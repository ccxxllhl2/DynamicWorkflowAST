"""API routes — pipeline orchestration + artifact management + execution."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from agentir.agents.registry import AgentRegistry as AgentReg
from agentir.artifacts.run_store import RunHistoryStore
from agentir.artifacts.runner import WorkflowRunner, _extract_node_logs
from agentir.artifacts.store import WorkflowArtifactStore
from agentir.compiler.adk import ADKCompiler
from agentir.llm.config import AgentConfig, LLMConfig
from agentir.planner import Planner
from agentir.server.config import ServerConfig
from agentir.server.models import (
    AgentConfigOverride,
    HealthResponse,
    NodeLogEntryModel,
    PlanResultInfo,
    RunHistoryResponse,
    RunRecordModel,
    ValidationReportInfo,
    WorkflowDetailResponse,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowGenerateOptions,
    WorkflowListItem,
    WorkflowListResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from agentir.tools.registry import ToolRegistry
from agentir.validator import validate_workflow

# ---- Router ----

router = APIRouter(prefix="/api/v1", tags=["workflows"])


# ---- Dependencies ----

def get_server_config(request: Request) -> ServerConfig:
    """Retrieve the server configuration from application state."""
    return request.app.state.config  # type: ignore[no-any-return]


def get_artifact_store(request: Request) -> WorkflowArtifactStore:
    """Retrieve the artifact store from application state."""
    return request.app.state.artifact_store  # type: ignore[no-any-return]


def get_tool_registry(request: Request) -> ToolRegistry:
    """Retrieve the tool registry from application state."""
    return request.app.state.tool_registry  # type: ignore[no-any-return]


def get_agent_registry(request: Request) -> AgentReg:
    """Retrieve the agent registry from application state."""
    return request.app.state.agent_registry  # type: ignore[no-any-return]


def get_run_store(request: Request) -> RunHistoryStore:
    """Retrieve (or lazily create) the run history store."""
    if not hasattr(request.app.state, "run_store"):
        config: ServerConfig = request.app.state.config
        request.app.state.run_store = RunHistoryStore(config.artifacts_dir)
    return request.app.state.run_store  # type: ignore[no-any-return]


# ---- Helpers ----

def _build_planner_from_config(
    config: ServerConfig,
    options: WorkflowGenerateOptions | None = None,
) -> Planner:
    """Build a Planner instance from server config + optional per-request overrides."""
    llm_config = _apply_options(config.llm, options)
    return Planner(
        llm_config=llm_config,
        max_retries=options.max_retries if options else 3,
    )


def _apply_options(
    base: LLMConfig,
    options: WorkflowGenerateOptions | None,
) -> LLMConfig:
    """Apply per-request option overrides to the base LLMConfig."""
    if options is None:
        return base

    # Build a copy with overrides
    overrides: dict = {}
    if options.model:
        overrides["model"] = options.model
    if options.temperature is not None:
        overrides["temperature"] = options.temperature

    if overrides:
        base = LLMConfig(
            provider=base.provider,
            api_key=base.api_key,
            base_url=base.base_url,
            model=overrides.get("model", base.model),
            temperature=overrides.get("temperature", base.temperature),
            max_tokens=base.max_tokens,
            extra_headers=dict(base.extra_headers),
            extra_body=dict(base.extra_body),
            agent_configs=dict(base.agent_configs),
            default_agent_model=base.default_agent_model,
            default_agent_instruction=base.default_agent_instruction,
        )

    # Apply agent overrides
    if options.agent_overrides:
        for override in options.agent_overrides:
            base.agent_configs[override.agent_name] = AgentConfig(
                agent_name=override.agent_name,
                model=override.model or base.default_agent_model,
                instruction=override.instruction or base.default_agent_instruction,
                tools=override.tools,
                temperature=override.temperature,
            )

    return base


def _build_plan_result_info(result) -> PlanResultInfo:
    """Build PlanResultInfo from a Planner PlanResult."""
    if result.workflow:
        return PlanResultInfo(
            success=result.success,
            workflow_name=result.workflow.name,
            workflow_version=result.workflow.version,
            workflow_description=result.workflow.description or "",
            retries=result.retries,
            errors=result.errors,
        )
    return PlanResultInfo(
        success=result.success,
        retries=result.retries,
        errors=result.errors,
    )


def _build_validation_info(report) -> ValidationReportInfo:
    """Build ValidationReportInfo from a Validator report."""
    return ValidationReportInfo(
        is_valid=report.is_valid,
        error_count=len(report.errors),
        warning_count=len(report.warnings),
        errors=[str(e) for e in report.errors],
        warnings=[str(w) for w in report.warnings],
    )


def _build_list_item(record) -> WorkflowListItem:
    """Build WorkflowListItem from a WorkflowRecord."""
    return WorkflowListItem(
        workflow_id=record.workflow_id,
        name=record.name,
        description=record.description,
        requirement=record.requirement,
        created_at=record.created_at,
        status=record.status,
        elapsed_ms=record.elapsed_ms,
        error=record.error,
    )


# ---- Health Check ----

@router.get("/health", response_model=HealthResponse)
def health_check(
    config: Annotated[ServerConfig, Depends(get_server_config)],
    tools: Annotated[ToolRegistry, Depends(get_tool_registry)],
    agents: Annotated[AgentReg, Depends(get_agent_registry)],
) -> HealthResponse:
    """Check if the server is running and LLM configuration status."""
    return HealthResponse(
        status="ok",
        version=config.version,
        provider=config.llm.provider,
        model=config.llm.model,
        base_url=config.llm.base_url,
        api_key_configured=bool(config.llm.api_key),
        artifacts_dir=str(config.artifacts_dir.resolve()),
        tools_count=len(tools.tools),
        agents_count=len(agents.agents),
    )


# ---- List Tools ----

@router.get(
    "/tools",
    summary="List available user-defined tools",
    description="Returns all tools discovered in the tools directory.",
)
def list_tools(
    tools: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> list[dict]:
    """List all registered tools with their metadata."""
    result = []
    for info in tools.list_tools():
        result.append({
            "name": info.name,
            "function": info.function,
            "description": info.description,
            "input_params": info.input_params,
            "output_type": info.output_type,
            "path": info.path,
        })
    return result


# ---- List Agents ----

@router.get(
    "/agents",
    summary="List pre-defined agents",
    description="Returns all agents discovered in the agents/ directory with their instructions.",
)
def list_agents(
    agents: Annotated[AgentReg, Depends(get_agent_registry)],
) -> list[dict]:
    """List all registered agents with their metadata."""
    result = []
    for name in agents.list_names():
        ag = agents.get(name)
        if ag:
            result.append({
                "name": ag.name,
                "instruction": ag.instruction,
                "model": ag.model,
                "temperature": ag.temperature,
            })
    return result


# ---- Core Endpoint: Generate Workflow ----

@router.post(
    "/workflows/generate",
    response_model=WorkflowGenerateResponse,
    summary="Generate an ADK workflow from natural language",
    description=(
        "Submit a natural language requirement description, and get back a complete "
        "ADK 2.0 workflow.\n\n"
        "Pipeline: **NL → Planner → AgentIR → Validator → ADK Compiler → Save**\n\n"
        "Returns a unique `workflow_id` — use it to **list** or **run** the workflow later.\n\n"
        "Persisted artifacts:\n"
        "- Requirement text → `artifacts/requirements/{workflow_id}.txt`\n"
        "- AgentIR Schema  → `artifacts/ir/{workflow_id}.json`\n"
        "- Runnable script → `artifacts/outputs/{workflow_id}.py`\n"
        "- Index entry     → `artifacts/index.json`"
    ),
)
def generate_workflow(
    body: WorkflowGenerateRequest,
    config: Annotated[ServerConfig, Depends(get_server_config)],
    store: Annotated[WorkflowArtifactStore, Depends(get_artifact_store)],
    tools: Annotated[ToolRegistry, Depends(get_tool_registry)],
    agents: Annotated[AgentReg, Depends(get_agent_registry)],
) -> WorkflowGenerateResponse:
    """Generate an ADK workflow from a natural language description, and persist it.

    Full pipeline: NL → Planner (LLM) → AgentIR → Validator → ADK Compiler → Save.
    """
    t_start = time.perf_counter()

    # ---- Step 1: Planning (NL → AgentIR) ----
    try:
        planner = _build_planner_from_config(config, body.options)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    result = planner.plan(
        body.requirement,
        available_agents=agents,
        available_tools=tools,
    )

    plan_info = _build_plan_result_info(result)

    if not result.success:
        elapsed = (time.perf_counter() - t_start) * 1000.0
        return WorkflowGenerateResponse(
            success=False,
            plan_result=plan_info,
            elapsed_ms=round(elapsed, 1),
        )

    workflow = result.workflow
    assert workflow is not None  # Guaranteed by result.success

    # ---- Step 2: Validation ----
    report = validate_workflow(workflow, tool_registry=tools)
    validation_info = _build_validation_info(report)

    if not report.is_valid:
        elapsed = (time.perf_counter() - t_start) * 1000.0
        return WorkflowGenerateResponse(
            success=False,
            plan_result=plan_info,
            agentir_json=workflow.model_dump(mode="python"),
            validation_report=validation_info,
            elapsed_ms=round(elapsed, 1),
        )

    # ---- Step 3: Compilation (AgentIR → ADK 2.0) ----
    agent_configs = config.llm.agent_configs if config.llm.agent_configs else None
    compiler_result = ADKCompiler().compile(
        workflow,
        agent_configs=agent_configs,
        tools_dir=str(config.tools_dir),
    )

    elapsed = (time.perf_counter() - t_start) * 1000.0

    # ---- Step 4: Persist artifacts ----
    workflow_id = ""
    if compiler_result.success and compiler_result.source_code:
        record = store.save_workflow(
            requirement=body.requirement,
            source_code=compiler_result.source_code,
            agentir_json=workflow.model_dump(mode="python"),
            name=plan_info.workflow_name,
            description=plan_info.workflow_description,
            elapsed_ms=round(elapsed, 1),
        )
        workflow_id = record.workflow_id

    return WorkflowGenerateResponse(
        workflow_id=workflow_id,
        success=compiler_result.success,
        plan_result=plan_info,
        agentir_json=workflow.model_dump(mode="python"),
        validation_report=validation_info,
        adk_source_code=compiler_result.source_code if compiler_result.success else None,
        compilation_errors=compiler_result.errors if not compiler_result.success else [],
        elapsed_ms=round(elapsed, 1),
    )


# ---- List Workflows ----

@router.get(
    "/workflows",
    response_model=WorkflowListResponse,
    summary="List all generated workflows",
    description=(
        "Returns a paginated list of previously generated workflows. "
        "Each item includes the ``workflow_id`` needed to **run** the workflow."
    ),
)
def list_workflows(
    store: Annotated[WorkflowArtifactStore, Depends(get_artifact_store)],
    offset: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(20, ge=1, le=100, description="Page size (max 100)."),
) -> WorkflowListResponse:
    """List all persisted workflows, newest first."""
    records, total = store.list_workflows(offset=offset, limit=limit)
    items = [_build_list_item(r) for r in records]
    return WorkflowListResponse(
        total=total,
        offset=offset,
        limit=limit,
        items=items,
    )


# ---- Get Workflow Detail ----

@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowDetailResponse,
    summary="Get workflow detail with AgentIR JSON",
    description=(
        "Returns full workflow metadata plus the AgentIR intermediate representation. "
        "Use this to render the workflow graph in a frontend."
    ),
)
def get_workflow(
    workflow_id: str,
    store: Annotated[WorkflowArtifactStore, Depends(get_artifact_store)],
) -> WorkflowDetailResponse:
    """Get a single workflow's full detail."""
    record = store.get_workflow(workflow_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_id}' not found.",
        )

    # Load AgentIR JSON from ir/ directory
    agentir_json = None
    ir_path = store._root / store.IR_DIR / f"{workflow_id}.json"
    if ir_path.is_file():
        try:
            import json as _json
            agentir_json = _json.loads(ir_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    return WorkflowDetailResponse(
        workflow_id=record.workflow_id,
        name=record.name,
        description=record.description,
        requirement=record.requirement,
        created_at=record.created_at,
        status=record.status,
        elapsed_ms=record.elapsed_ms,
        error=record.error,
        agentir_json=agentir_json,
    )


# ---- Get Run History ----

@router.get(
    "/workflows/{workflow_id}/runs",
    response_model=RunHistoryResponse,
    summary="Get run history for a workflow",
    description=(
        "Returns all execution runs for a workflow, including per-node logs. "
        "Runs are sorted newest first."
    ),
)
def get_run_history(
    workflow_id: str,
    store: Annotated[WorkflowArtifactStore, Depends(get_artifact_store)],
    run_store: Annotated[RunHistoryStore, Depends(get_run_store)],
) -> RunHistoryResponse:
    """Get run history for a workflow."""
    # Verify workflow exists
    record = store.get_workflow(workflow_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_id}' not found.",
        )

    runs = run_store.get_runs(workflow_id)
    run_models = [
        RunRecordModel(
            run_id=r.run_id,
            workflow_id=r.workflow_id,
            started_at=r.started_at,
            finished_at=r.finished_at,
            elapsed_ms=r.elapsed_ms,
            success=r.success,
            exit_code=r.exit_code,
            node_logs=[
                NodeLogEntryModel(node=nl.node, kind=nl.kind, event=nl.event, data=nl.data)
                for nl in r.node_logs
            ],
            log_path=r.log_path,
            error=r.error,
        )
        for r in runs
    ]

    return RunHistoryResponse(workflow_id=workflow_id, runs=run_models)


# ---- Run Workflow ----

@router.post(
    "/workflows/{workflow_id}/run",
    response_model=WorkflowRunResponse,
    summary="Execute a generated workflow",
    description=(
        "Run a previously generated workflow by its ``workflow_id``.\n\n"
        "The workflow script is executed in a subprocess with:\n"
        "- Full stdout/stderr capture\n"
        "- A structured log file written to ``artifacts/logs/``\n"
        "- Optional stdin input via ``input_text``\n"
        "- Configurable timeout"
    ),
)
def run_workflow(
    workflow_id: str,
    body: WorkflowRunRequest,
    config: Annotated[ServerConfig, Depends(get_server_config)],
    store: Annotated[WorkflowArtifactStore, Depends(get_artifact_store)],
    run_store: Annotated[RunHistoryStore, Depends(get_run_store)],
) -> WorkflowRunResponse:
    """Execute a previously generated workflow by ID."""
    # Look up the workflow
    record = store.get_workflow(workflow_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Workflow '{workflow_id}' not found. "
            f"Use GET /api/v1/workflows to list available workflows.",
        )

    script_path = store.get_source_path(workflow_id)
    if script_path is None or not script_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Workflow script for '{workflow_id}' not found on disk.",
        )

    # Update status to running
    store.update_status(workflow_id, status="running")

    # Execute
    logs_dir = config.artifacts_dir / "logs"
    runner = WorkflowRunner(logs_dir=logs_dir)
    result = runner.run(
        workflow_id=workflow_id,
        script_path=script_path,
        input_text=body.input_text,
        timeout_seconds=body.timeout_seconds,
    )

    # Update status
    final_status = "completed" if result.success else "failed"
    error_msg = result.errors[0] if result.errors else ""
    store.update_status(workflow_id, status=final_status, error=error_msg)

    # Make log_path relative to artifacts dir
    log_path_rel = result.log_path
    try:
        log_path_rel = str(Path(result.log_path).relative_to(config.artifacts_dir))
    except ValueError:
        pass

    # Persist run history
    node_log_dicts: list[dict[str, str]] = [
        {"node": nl.node, "kind": nl.kind, "event": nl.event, "data": nl.data}
        for nl in result.node_logs
    ]
    run_store.save_run(
        workflow_id=workflow_id,
        started_at=result.started_at,
        finished_at=result.finished_at,
        elapsed_ms=result.elapsed_ms,
        success=result.success,
        exit_code=result.exit_code,
        node_logs=node_log_dicts,
        log_path=log_path_rel,
        error=error_msg,
    )

    node_log_models = [
        NodeLogEntryModel(node=nl.node, kind=nl.kind, event=nl.event, data=nl.data)
        for nl in result.node_logs
    ]

    return WorkflowRunResponse(
        success=result.success,
        workflow_id=result.workflow_id,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        node_logs=node_log_models,
        log_path=log_path_rel,
        started_at=result.started_at,
        finished_at=result.finished_at,
        elapsed_ms=result.elapsed_ms,
        errors=result.errors,
    )
