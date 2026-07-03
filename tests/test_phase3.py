"""Tests for Phase 3: Interactive AgentIR Editor + Bidirectional Sync.

Tests the new PUT /api/v1/workflows/{id}/ir and
POST /api/v1/workflows/{id}/ir/validate endpoints.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agentir.agents.registry import AgentRegistry
from agentir.artifacts.store import WorkflowArtifactStore
from agentir.ir.nodes import AgentNode, SequenceNode, WorkflowNode
from agentir.ir.models import WorkflowDefinition
from agentir.ir.schema import workflow_from_dict
from agentir.server.config import ServerConfig
from agentir.server.main import create_app
from agentir.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sample_ir() -> dict:
    """Return a minimal valid AgentIR dict."""
    return {
        "name": "test_workflow",
        "version": "0.1.0",
        "description": "A test workflow",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "agent", "agent": "writer"},
            ],
        },
    }


def _make_client(tmp_path) -> tuple[TestClient, WorkflowArtifactStore]:
    """Create a FastAPI test client with an in-memory artifact store."""
    from agentir.llm.config import LLMConfig

    artifacts_dir = tmp_path / "artifacts"
    tools_dir = tmp_path / "tools"
    agents_dir = tmp_path / "agents"
    tools_dir.mkdir(exist_ok=True)
    agents_dir.mkdir(exist_ok=True)

    # Create a dummy LLMConfig (no real API key needed for these tests)
    llm_config = LLMConfig(
        provider="custom",
        api_key="test-key",
        base_url="http://localhost:8000",
        model="test-model",
    )

    config = ServerConfig(
        llm=llm_config,
        artifacts_dir=artifacts_dir,
        tools_dir=tools_dir,
        agents_dir=agents_dir,
    )

    app = create_app(config)

    # Ensure registries and store are on app state
    if not hasattr(app.state, "tool_registry"):
        app.state.tool_registry = ToolRegistry.from_directory(tools_dir)
    if not hasattr(app.state, "agent_registry"):
        app.state.agent_registry = AgentRegistry.from_directory(agents_dir)
    store = WorkflowArtifactStore(str(artifacts_dir))
    app.state.artifact_store = store

    return TestClient(app), store


# ---------------------------------------------------------------------------
# Tests: PUT /api/v1/workflows/{id}/ir
# ---------------------------------------------------------------------------

def test_update_ir_not_found(tmp_path):
    """Updating a non-existent workflow should return 404."""
    client, _ = _make_client(tmp_path)
    resp = client.put("/api/v1/workflows/nonexistent/ir", json={
        "agentir_json": _make_sample_ir(),
    })
    assert resp.status_code == 404


def test_update_ir_success(tmp_path):
    """Updating an existing workflow should validate, compile, and save."""
    client, store = _make_client(tmp_path)

    # First, create a workflow via the store directly
    ir = _make_sample_ir()
    record = store.save_workflow(
        requirement="test requirement",
        source_code="# test code",
        agentir_json=ir,
        name="test_workflow",
        description="test",
    )

    # Update the IR (add a step)
    updated_ir = {
        "name": "test_workflow",
        "version": "0.1.0",
        "description": "Updated workflow",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "agent", "agent": "analyst"},
                {"type": "agent", "agent": "writer"},
            ],
        },
    }

    resp = client.put(f"/api/v1/workflows/{record.workflow_id}/ir", json={
        "agentir_json": updated_ir,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["workflow_id"] == record.workflow_id
    assert data["agentir_json"] is not None
    assert data["adk_source_code"] is not None
    assert "analyst" in data["adk_source_code"]

    # Verify the IR was saved to disk
    ir_path = store._ir_dir / f"{record.workflow_id}.json"
    assert ir_path.is_file()
    saved_ir = json.loads(ir_path.read_text())
    assert saved_ir["root"]["steps"][1]["agent"] == "analyst"


def test_update_ir_validation_fails(tmp_path):
    """Updating with invalid AgentIR should return validation errors."""
    client, store = _make_client(tmp_path)

    ir = _make_sample_ir()
    record = store.save_workflow(
        requirement="test",
        source_code="# test",
        agentir_json=ir,
        name="test",
    )

    # Invalid IR: empty sequence
    invalid_ir = {
        "name": "bad",
        "version": "0.1.0",
        "description": "bad",
        "root": {
            "type": "sequence",
            "steps": [],
        },
    }

    resp = client.put(f"/api/v1/workflows/{record.workflow_id}/ir", json={
        "agentir_json": invalid_ir,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["validation_report"]["is_valid"] is False
    assert data["validation_report"]["error_count"] > 0


def test_update_ir_invalid_json(tmp_path):
    """Updating with malformed JSON should return compilation errors."""
    client, store = _make_client(tmp_path)

    ir = _make_sample_ir()
    record = store.save_workflow(
        requirement="test",
        source_code="# test",
        agentir_json=ir,
        name="test",
    )

    # Missing required field "root"
    bad_ir = {"name": "bad", "version": "0.1.0", "description": "bad"}

    resp = client.put(f"/api/v1/workflows/{record.workflow_id}/ir", json={
        "agentir_json": bad_ir,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


# ---------------------------------------------------------------------------
# Tests: POST /api/v1/workflows/{id}/ir/validate
# ---------------------------------------------------------------------------

def test_validate_ir_ok(tmp_path):
    """Validating a valid IR should return no errors."""
    client, store = _make_client(tmp_path)

    ir = _make_sample_ir()
    record = store.save_workflow(
        requirement="test",
        source_code="# test",
        agentir_json=ir,
        name="test",
    )

    resp = client.post(f"/api/v1/workflows/{record.workflow_id}/ir/validate", json={
        "agentir_json": ir,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["error_count"] == 0


def test_validate_ir_bad(tmp_path):
    """Validating an invalid IR should return errors."""
    client, store = _make_client(tmp_path)

    ir = _make_sample_ir()
    record = store.save_workflow(
        requirement="test",
        source_code="# test",
        agentir_json=ir,
        name="test",
    )

    bad_ir = {"name": "bad", "version": "0.1.0", "description": "bad", "root": None}

    resp = client.post(f"/api/v1/workflows/{record.workflow_id}/ir/validate", json={
        "agentir_json": bad_ir,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is False


# ---------------------------------------------------------------------------
# Tests: Artifact Store update methods
# ---------------------------------------------------------------------------

def test_store_update_ir(tmp_path):
    """Test WorkflowArtifactStore.update_workflow_ir."""
    store = WorkflowArtifactStore(str(tmp_path / "artifacts"))

    ir = _make_sample_ir()
    record = store.save_workflow(
        requirement="test",
        source_code="# test",
        agentir_json=ir,
        name="test",
    )

    new_ir = _make_sample_ir()
    new_ir["root"]["steps"].append({"type": "agent", "agent": "reviewer"})

    updated = store.update_workflow_ir(record.workflow_id, new_ir)
    assert updated is not None
    assert updated.workflow_id == record.workflow_id

    # Verify file on disk
    ir_path = store._ir_dir / f"{record.workflow_id}.json"
    saved = json.loads(ir_path.read_text())
    assert len(saved["root"]["steps"]) == 3


def test_store_update_source(tmp_path):
    """Test WorkflowArtifactStore.update_workflow_source."""
    store = WorkflowArtifactStore(str(tmp_path / "artifacts"))

    record = store.save_workflow(
        requirement="test",
        source_code="# old code",
        agentir_json=_make_sample_ir(),
        name="test",
    )

    updated = store.update_workflow_source(record.workflow_id, "# new code")
    assert updated is not None

    src_path = store._outputs_dir / f"{record.workflow_id}.py"
    assert src_path.read_text() == "# new code"


def test_store_update_nonexistent(tmp_path):
    """Updating a non-existent workflow should return None."""
    store = WorkflowArtifactStore(str(tmp_path / "artifacts"))
    assert store.update_workflow_ir("nonexistent", _make_sample_ir()) is None
    assert store.update_workflow_source("nonexistent", "# code") is None


# ---------------------------------------------------------------------------
# Tests: IR tree operations (ir-tree-ops.ts equivalent in Python)
# ---------------------------------------------------------------------------

def test_workflow_from_dict_roundtrip():
    """WorkflowDefinition can be serialized and deserialized."""
    ir_dict = _make_sample_ir()
    wf = workflow_from_dict(ir_dict)
    assert wf.name == "test_workflow"
    assert isinstance(wf.root, SequenceNode)
    assert len(wf.root.steps) == 2

    # Round-trip
    dumped = wf.model_dump(mode="python")
    wf2 = workflow_from_dict(dumped)
    assert wf2.name == wf.name
    assert len(wf2.root.steps) == len(wf.root.steps)


def test_workflow_node_modification():
    """WorkflowDefinition nodes can be mutated in place."""
    ir_dict = _make_sample_ir()
    wf = workflow_from_dict(ir_dict)

    # Add a step
    assert isinstance(wf.root, SequenceNode)
    wf.root.steps.append(AgentNode(agent="reviewer"))
    assert len(wf.root.steps) == 3

    # Change an agent name
    wf.root.steps[0].agent = "super_researcher"
    assert wf.root.steps[0].agent == "super_researcher"


def test_condition_node_roundtrip():
    """ConditionNode serializes and deserializes correctly."""
    ir_dict = {
        "name": "cond_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "condition",
            "expression": "output.needs_review",
            "true_branch": {"type": "agent", "agent": "reviewer"},
            "false_branch": {"type": "agent", "agent": "publisher"},
        },
    }
    wf = workflow_from_dict(ir_dict)
    dumped = wf.model_dump(mode="python")
    assert dumped["root"]["expression"] == "output.needs_review"
    assert dumped["root"]["true_branch"]["agent"] == "reviewer"


def test_loop_node_roundtrip():
    """LoopNode serializes and deserializes correctly."""
    ir_dict = {
        "name": "loop_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "loop",
            "max_iterations": 5,
            "body": {"type": "agent", "agent": "checker"},
        },
    }
    wf = workflow_from_dict(ir_dict)
    assert wf.root.max_iterations == 5
    dumped = wf.model_dump(mode="python")
    assert dumped["root"]["max_iterations"] == 5


# ============================================================
# Phase 4: SubWorkflow nodes, validation, cycle detection
# ============================================================

def test_subworkflow_node_roundtrip():
    """SubWorkflowNode serializes and deserializes correctly."""
    ir_dict = {
        "name": "swf_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "subworkflow",
            "workflow": "data_pipeline",
        },
    }
    wf = workflow_from_dict(ir_dict)
    assert wf.root.type == "subworkflow"
    assert wf.root.workflow == "data_pipeline"
    dumped = wf.model_dump(mode="python")
    assert dumped["root"]["workflow"] == "data_pipeline"


def test_subworkflow_node_in_sequence():
    """SubWorkflowNode works inside a sequence."""
    ir_dict = {
        "name": "swf_seq",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "subworkflow", "workflow": "data_pipeline"},
                {"type": "agent", "agent": "writer"},
            ],
        },
    }
    wf = workflow_from_dict(ir_dict)
    assert len(wf.root.steps) == 3
    assert wf.root.steps[1].type == "subworkflow"


def test_validator_handles_subworkflow():
    """Validator's structural rules work with subworkflow nodes."""
    from agentir.validator import validate_workflow

    ir_dict = {
        "name": "swf_valid",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "subworkflow", "workflow": "data_pipeline"},
            ],
        },
    }
    wf = workflow_from_dict(ir_dict)
    report = validate_workflow(wf)
    assert report.is_valid


def test_subworkflow_existence_check():
    """validate_subworkflow_existence detects missing sub-workflows."""
    from agentir.validator.rules import (
        SubWorkflowRegistry,
        validate_subworkflow_existence,
    )

    ir_dict = {
        "name": "swf_missing",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "subworkflow",
            "workflow": "nonexistent_pipeline",
        },
    }
    wf = workflow_from_dict(ir_dict)
    registry = SubWorkflowRegistry.empty()
    errors = validate_subworkflow_existence(wf, registry)
    assert len(errors) == 1
    assert errors[0].code == "SUBWORKFLOW_NOT_FOUND"


def test_subworkflow_existence_pass():
    """validate_subworkflow_existence passes for registered sub-workflows."""
    from agentir.validator.rules import (
        SubWorkflowRegistry,
        validate_subworkflow_existence,
    )

    sub_wf = workflow_from_dict({
        "name": "data_pipeline",
        "version": "0.1.0",
        "description": "sub",
        "root": {"type": "agent", "agent": "processor"},
    })
    registry = SubWorkflowRegistry(workflows={"data_pipeline": sub_wf})

    parent_wf = workflow_from_dict({
        "name": "parent",
        "version": "0.1.0",
        "description": "test",
        "root": {"type": "subworkflow", "workflow": "data_pipeline"},
    })
    errors = validate_subworkflow_existence(parent_wf, registry)
    assert len(errors) == 0


def test_no_subworkflow_cycle():
    """validate_no_subworkflow_cycles passes when no cycles exist."""
    from agentir.validator.rules import (
        SubWorkflowRegistry,
        validate_no_subworkflow_cycles,
    )

    sub_wf = workflow_from_dict({
        "name": "data_pipeline",
        "version": "0.1.0",
        "description": "sub",
        "root": {"type": "agent", "agent": "processor"},
    })
    registry = SubWorkflowRegistry(workflows={"data_pipeline": sub_wf})

    parent_wf = workflow_from_dict({
        "name": "parent",
        "version": "0.1.0",
        "description": "test",
        "root": {"type": "subworkflow", "workflow": "data_pipeline"},
    })
    errors = validate_no_subworkflow_cycles(parent_wf, registry)
    assert len(errors) == 0


def test_subworkflow_cycle_detected():
    """validate_no_subworkflow_cycles detects circular references."""
    from agentir.validator.rules import (
        SubWorkflowRegistry,
        validate_no_subworkflow_cycles,
    )

    # A references B, B references A
    wf_a = workflow_from_dict({
        "name": "wf_a",
        "version": "0.1.0",
        "description": "A",
        "root": {"type": "subworkflow", "workflow": "wf_b"},
    })
    wf_b = workflow_from_dict({
        "name": "wf_b",
        "version": "0.1.0",
        "description": "B",
        "root": {"type": "subworkflow", "workflow": "wf_a"},
    })
    registry = SubWorkflowRegistry(workflows={"wf_a": wf_a, "wf_b": wf_b})

    errors = validate_no_subworkflow_cycles(wf_a, registry)
    assert len(errors) == 1
    assert errors[0].code == "SUBWORKFLOW_CYCLE"


def test_subworkflow_self_cycle():
    """validate_no_subworkflow_cycles detects self-referencing workflows."""
    from agentir.validator.rules import (
        SubWorkflowRegistry,
        validate_no_subworkflow_cycles,
    )

    wf_self = workflow_from_dict({
        "name": "self_ref",
        "version": "0.1.0",
        "description": "self",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "do_stuff"},
                {"type": "subworkflow", "workflow": "self_ref"},
            ],
        },
    })
    registry = SubWorkflowRegistry(workflows={"self_ref": wf_self})

    errors = validate_no_subworkflow_cycles(wf_self, registry)
    assert len(errors) == 1
    assert errors[0].code == "SUBWORKFLOW_CYCLE"


def test_adk_compiler_handles_subworkflow():
    """ADKCompiler generates code for workflows containing SubWorkflowNode."""
    from agentir.compiler.adk import ADKCompiler

    wf = workflow_from_dict({
        "name": "test_swf",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "subworkflow", "workflow": "data_pipeline"},
            ],
        },
    })
    result = ADKCompiler().compile(wf)
    assert result.success
    assert "sub_workflow_data_pipeline" in result.source_code
    assert "researcher" in result.source_code


def test_adk_compiler_subworkflow_with_resolver():
    """ADKCompiler resolves and inlines sub-workflow code."""
    from agentir.compiler.adk import ADKCompiler

    sub_wf = workflow_from_dict({
        "name": "data_pipeline",
        "version": "0.1.0",
        "description": "sub pipeline",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "processor"},
                {"type": "agent", "agent": "validator"},
            ],
        },
    })

    def resolver(name: str):
        if name == "data_pipeline":
            return sub_wf
        return None

    parent_wf = workflow_from_dict({
        "name": "parent",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "subworkflow",
            "workflow": "data_pipeline",
        },
    })
    result = ADKCompiler().compile(parent_wf, subworkflow_resolver=resolver)
    assert result.success
    assert "sub_workflow_data_pipeline" in result.source_code
    # Should contain the sub-workflow's agent code
    assert "processor" in result.source_code
    assert "validator" in result.source_code


def test_max_depth_handles_subworkflow():
    """validate_max_depth treats SubWorkflowNode as leaf."""
    from agentir.validator.rules import validate_max_depth

    wf = workflow_from_dict({
        "name": "depth_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "subworkflow",
            "workflow": "deep",
        },
    })
    errors = validate_max_depth(wf, max_depth=1)
    assert len(errors) == 0  # depth is 1, not exceeded


# ============================================================
# Phase 5: LangGraph Compiler
# ============================================================

def test_langgraph_compiler_basic_sequence():
    """LangGraphCompiler generates code for a simple sequence."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "simple_seq",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "agent", "agent": "writer"},
            ],
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    assert result.runtime == "langgraph"
    code = result.source_code
    assert "StateGraph" in code
    assert "researcher_node" in code
    assert "writer_node" in code
    assert "add_edge" in code
    assert "graph.compile()" in code


def test_langgraph_compiler_condition():
    """LangGraphCompiler generates conditional_edges for conditions."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "cond_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "condition",
            "expression": "output.needs_review",
            "true_branch": {"type": "agent", "agent": "reviewer"},
            "false_branch": {"type": "agent", "agent": "publisher"},
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    assert "add_conditional_edges" in result.source_code
    assert "reviewer_node" in result.source_code
    assert "publisher_node" in result.source_code


def test_langgraph_compiler_loop():
    """LangGraphCompiler generates loop routing for loops."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "loop_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "loop",
            "max_iterations": 3,
            "body": {"type": "agent", "agent": "checker"},
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    assert "loop_count" in result.source_code
    assert "checker_node" in result.source_code


def test_langgraph_compiler_parallel():
    """LangGraphCompiler generates fork/join for parallel nodes."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "parallel_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "parallel",
            "branches": [
                {"type": "agent", "agent": "worker_a"},
                {"type": "agent", "agent": "worker_b"},
            ],
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    assert "__fork_" in result.source_code
    assert "__join_" in result.source_code
    assert "worker_a_node" in result.source_code
    assert "worker_b_node" in result.source_code


def test_langgraph_compiler_tool():
    """LangGraphCompiler handles tool nodes."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "tool_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "tool", "tool": "web_search"},
                {"type": "agent", "agent": "analyst"},
            ],
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    assert "web_search_node" in result.source_code
    assert "analyst_node" in result.source_code


def test_langgraph_compiler_subworkflow():
    """LangGraphCompiler handles subworkflow nodes."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "swf_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "subworkflow", "workflow": "data_pipeline"},
            ],
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    assert "sub_data_pipeline" in result.source_code


def test_langgraph_compiler_complex():
    """LangGraphCompiler handles a complex nested workflow."""
    from agentir.compiler.langgraph import LangGraphCompiler

    wf = workflow_from_dict({
        "name": "complex",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {
                    "type": "condition",
                    "expression": "output.needs_review",
                    "true_branch": {
                        "type": "loop",
                        "max_iterations": 3,
                        "body": {"type": "agent", "agent": "reviewer"},
                    },
                    "false_branch": {"type": "agent", "agent": "writer"},
                },
                {"type": "agent", "agent": "publisher"},
            ],
        },
    })
    result = LangGraphCompiler().compile(wf)
    assert result.success
    code = result.source_code
    assert "researcher_node" in code
    assert "reviewer_node" in code
    assert "writer_node" in code
    assert "publisher_node" in code
    assert "add_conditional_edges" in code


# ============================================================
# Phase 5: CrewAI Compiler
# ============================================================

def test_crewai_compiler_basic():
    """CrewAICompiler generates code for a simple sequence."""
    from agentir.compiler.crewai import CrewAICompiler

    wf = workflow_from_dict({
        "name": "crew_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "pi"},
                {"type": "agent", "agent": "researcher"},
            ],
        },
    })
    result = CrewAICompiler().compile(wf)
    assert result.success
    assert result.runtime == "crewai"
    code = result.source_code
    assert "Agent(" in code
    assert "Task(" in code
    assert "Crew(" in code
    assert "Process.sequential" in code
    assert "pi" in code
    assert "researcher" in code
    assert "crew.kickoff" in code


def test_crewai_compiler_with_tools():
    """CrewAICompiler includes tool definitions."""
    from agentir.compiler.crewai import CrewAICompiler

    wf = workflow_from_dict({
        "name": "tool_test",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "tool", "tool": "web_search"},
                {"type": "agent", "agent": "analyst"},
            ],
        },
    })
    result = CrewAICompiler().compile(wf)
    assert result.success
    assert "web_search" in result.source_code


def test_crewai_compiler_complex():
    """CrewAICompiler handles a complex workflow with pi agent."""
    from agentir.compiler.crewai import CrewAICompiler

    wf = workflow_from_dict({
        "name": "complex_crew",
        "version": "0.1.0",
        "description": "test",
        "root": {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "pi"},
                {"type": "agent", "agent": "researcher"},
                {
                    "type": "condition",
                    "expression": "output.needs_review",
                    "true_branch": {
                        "type": "loop",
                        "max_iterations": 3,
                        "body": {"type": "agent", "agent": "reviewer"},
                    },
                    "false_branch": {"type": "agent", "agent": "writer"},
                },
            ],
        },
    })
    result = CrewAICompiler().compile(wf)
    assert result.success
    code = result.source_code
    assert "pi" in code
    assert "researcher" in code
    assert "reviewer" in code
    assert "writer" in code


# ============================================================
# Phase 5: PI Agent
# ============================================================

def test_pi_agent_registered():
    """PI agent is discoverable via AgentRegistry."""
    from agentir.agents.registry import AgentRegistry

    reg = AgentRegistry.from_directory("./agents")
    assert reg.has("pi")

    ag = reg.get("pi")
    assert ag is not None
    assert ag.name == "pi"
    assert "strategic process intelligence" in ag.instruction
    assert ag.model == "deepseek-chat"


def test_pi_agent_in_planner_context():
    """PI agent appears in planner prompt context."""
    from agentir.agents.registry import AgentRegistry

    reg = AgentRegistry.from_directory("./agents")
    ctx = reg.to_prompt_context()
    assert "pi" in ctx
    assert "strategic" in ctx.lower()
