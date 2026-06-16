"""API request/response models for the AgentIR server."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---- Request: Generate ----

class AgentConfigOverride(BaseModel):
    """Per-agent configuration override in the request."""

    agent_name: str = Field(..., description="Agent name to configure.")
    model: str = Field("", description="Model name for this agent.")
    instruction: str = Field("", description="Instruction/prompt for this agent.")
    tools: list[str] = Field(default_factory=list, description="Tool names.")
    temperature: float | None = Field(None, description="Sampling temperature.")


class WorkflowGenerateRequest(BaseModel):
    """Request to generate a workflow from a natural language description.

    Example:
        {
            "requirement": "先让研究员收集数据，然后审核最多3次，最后撰写并发布报告",
            "options": {
                "model": "deepseek-chat",
                "agent_overrides": [
                    {"agent_name": "researcher", "model": "deepseek-reasoner"}
                ]
            }
        }
    """

    requirement: str = Field(
        ...,
        description="Natural language description of the desired agent workflow.",
        min_length=1,
        examples=[
            "First have a researcher gather data. "
            "Then if output needs review, loop with a reviewer up to 3 times. "
            "Otherwise have a writer write the report. "
            "Finally a publisher publishes the result."
        ],
    )

    options: WorkflowGenerateOptions | None = Field(
        None,
        description="Optional generation options (model override, agent configs, etc.).",
    )


class WorkflowGenerateOptions(BaseModel):
    """Optional settings for workflow generation."""

    model: str = Field(
        "",
        description="Override the default LLM model for the planner step.",
        examples=["deepseek-chat", "gpt-4o", "deepseek-reasoner"],
    )
    temperature: float | None = Field(
        None,
        description="Sampling temperature for the planner (0.0–2.0).",
        ge=0.0,
        le=2.0,
    )
    max_retries: int = Field(
        3,
        description="Maximum retries on validation failure.",
        ge=0,
        le=10,
    )
    agent_overrides: list[AgentConfigOverride] = Field(
        default_factory=list,
        description="Per-agent model/instruction overrides for the compiled output.",
    )


# ---- Request: Run ----

class WorkflowRunRequest(BaseModel):
    """Request to execute a previously generated workflow."""

    input_text: str = Field(
        "",
        description="Initial input text to send to the workflow (passed via stdin).",
    )
    timeout_seconds: int = Field(
        300,
        description="Maximum execution time in seconds.",
        ge=10,
        le=3600,
    )


# ---- Response: Generate ----

class PlanResultInfo(BaseModel):
    """Summary of the Planner result."""

    success: bool = False
    workflow_name: str = ""
    workflow_version: str = ""
    workflow_description: str = ""
    retries: int = 0
    errors: list[str] = Field(default_factory=list)


class ValidationReportInfo(BaseModel):
    """Summary of the Validator report."""

    is_valid: bool = False
    error_count: int = 0
    warning_count: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowGenerateResponse(BaseModel):
    """Response containing the full pipeline output.

    Returns everything a user needs to inspect and deploy:
        - workflow_id (for later listing / running)
        - The intermediate AgentIR JSON (for audit/debugging)
        - The validation report
        - The final ADK 2.0 Python source code
        - A summary of the planning process
    """

    workflow_id: str = Field(
        "",
        description="Unique ID assigned to this workflow. Use to list or run later.",
    )
    success: bool = Field(
        ...,
        description="Whether the entire pipeline succeeded.",
    )
    plan_result: PlanResultInfo = Field(
        default_factory=PlanResultInfo,
        description="Summary of the NL→AgentIR planning step.",
    )
    agentir_json: dict[str, Any] | None = Field(
        None,
        description="The generated AgentIR workflow definition as JSON.",
    )
    validation_report: ValidationReportInfo = Field(
        default_factory=ValidationReportInfo,
        description="Validation report for the AgentIR definition.",
    )
    adk_source_code: str | None = Field(
        None,
        description="The compiled ADK 2.0 Python source code (runnable).",
    )
    compilation_errors: list[str] = Field(
        default_factory=list,
        description="Compilation errors, if any.",
    )
    elapsed_ms: float = Field(
        0.0,
        description="Total pipeline execution time in milliseconds.",
    )


# ---- Response: List ----

class WorkflowListItem(BaseModel):
    """A single workflow in the listing."""

    workflow_id: str = Field(..., description="Unique workflow ID.")
    name: str = Field("", description="Workflow name.")
    description: str = Field("", description="Workflow description.")
    requirement: str = Field("", description="Original natural language requirement.")
    created_at: str = Field("", description="ISO 8601 creation timestamp.")
    status: str = Field("generated", description="Current status.")
    elapsed_ms: float = Field(0.0, description="Generation time in ms.")
    error: str = Field("", description="Error message if status is 'failed'.")


class WorkflowListResponse(BaseModel):
    """Paginated list of generated workflows."""

    total: int = Field(..., description="Total number of workflows.")
    offset: int = Field(0, description="Current page offset.")
    limit: int = Field(20, description="Page size.")
    items: list[WorkflowListItem] = Field(
        default_factory=list,
        description="Workflow items in this page.",
    )


# ---- Response: Run ----

class WorkflowRunResponse(BaseModel):
    """Result of executing a workflow."""

    success: bool = Field(
        ...,
        description="Whether the workflow ran to completion (exit code 0).",
    )
    workflow_id: str = Field(..., description="Workflow ID that was run.")
    exit_code: int = Field(-1, description="Process exit code.")
    stdout: str = Field("", description="Standard output from the workflow.")
    stderr: str = Field("", description="Standard error from the workflow.")
    log_path: str = Field("", description="Relative path to the execution log file.")
    started_at: str = Field("", description="ISO 8601 start time.")
    finished_at: str = Field("", description="ISO 8601 finish time.")
    elapsed_ms: float = Field(0.0, description="Execution time in milliseconds.")
    errors: list[str] = Field(
        default_factory=list,
        description="Execution errors, if any.",
    )


# ---- Response: Health ----

class HealthResponse(BaseModel):
    """Health check response with current configuration status."""

    status: str = Field(..., description="'ok' if the server is running.")
    version: str = Field(..., description="AgentIR version.")
    provider: str = Field(..., description="Configured LLM provider.")
    model: str = Field(..., description="Configured LLM model.")
    base_url: str = Field(..., description="LLM API base URL.")
    api_key_configured: bool = Field(
        False,
        description="Whether an API key is set (masked for security).",
    )
    artifacts_dir: str = Field(
        "",
        description="Absolute path to the artifacts storage directory.",
    )
    tools_count: int = Field(
        0,
        description="Number of user-defined tools discovered.",
    )
