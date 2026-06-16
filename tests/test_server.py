"""Tests for the AgentIR FastAPI server."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---- Fixtures ----

@pytest.fixture
def temp_artifacts_dir():
    """Create a temporary artifacts directory."""
    with tempfile.TemporaryDirectory(prefix="agentir_test_") as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_llm_env(monkeypatch):
    """Set up environment variables for DeepSeek."""
    monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("AGENTIR_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")


@pytest.fixture
def temp_tools_dir():
    """Create a temporary tools directory."""
    with tempfile.TemporaryDirectory(prefix="agentir_tools_") as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_planner_success(monkeypatch):
    """Monkeypatch Planner.plan to return a successful result."""
    from agentir.ir.models import WorkflowDefinition
    from agentir.ir.nodes import AgentNode, SequenceNode
    from agentir.planner.planner import PlanResult

    wf = WorkflowDefinition(
        name="test_workflow",
        version="0.1.0",
        description="A test workflow.",
        root=SequenceNode(steps=[
            AgentNode(agent="researcher"),
            AgentNode(agent="writer"),
        ]),
    )

    result = PlanResult(
        workflow=wf,
        success=True,
        raw_response=json.dumps({"name": "test_workflow", "root": {}}),
        retries=0,
        errors=[],
    )

    def mock_plan(self, description: str, available_tools=None) -> PlanResult:
        return result

    monkeypatch.setattr("agentir.planner.Planner.plan", mock_plan)
    return result


@pytest.fixture
def mock_planner_failure(monkeypatch):
    """Monkeypatch Planner.plan to return a failure result."""
    from agentir.planner.planner import PlanResult

    result = PlanResult(
        success=False,
        retries=3,
        errors=["JSON parse error", "Validation failed"],
    )

    def mock_plan(self, description: str, available_tools=None) -> PlanResult:
        return result

    monkeypatch.setattr("agentir.planner.Planner.plan", mock_plan)
    return result


@pytest.fixture
def client(mock_llm_env, temp_artifacts_dir, temp_tools_dir):
    """Create a TestClient for the app with temp artifacts and tools directories."""
    from agentir.server.main import create_app
    from agentir.server.config import ServerConfig
    from agentir.tools.registry import ToolRegistry

    config = ServerConfig.from_env(
        artifacts_dir=temp_artifacts_dir,
        tools_dir=temp_tools_dir,
    )
    app = create_app(config)
    # Ensure tool registry is on app state (it's set in lifespan, but we bypass it in tests)
    if not hasattr(app.state, "tool_registry"):
        app.state.tool_registry = ToolRegistry.from_directory(temp_tools_dir)
    return TestClient(app)


# ---- Test: Health Check ----

class TestHealth:
    def test_health_ok(self, client, temp_artifacts_dir):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert data["provider"] == "deepseek"
        assert data["model"] == "deepseek-chat"
        assert "api.deepseek.com" in data["base_url"]
        assert data["api_key_configured"] is True
        assert data["artifacts_dir"] == str(temp_artifacts_dir.resolve())
        assert "tools_count" in data

    def test_health_provider_visible(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data
        assert "model" in data
        assert "base_url" in data
        assert "artifacts_dir" in data
        assert "tools_count" in data

    def test_health_no_api_key_shows_false(self, monkeypatch, temp_artifacts_dir, temp_tools_dir):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "")
        monkeypatch.setenv("AGENTIR_LLM_API_KEY", "")

        from agentir.server.main import create_app
        from agentir.server.config import ServerConfig
        from agentir.tools.registry import ToolRegistry

        config = ServerConfig.from_env(
            artifacts_dir=temp_artifacts_dir,
            tools_dir=temp_tools_dir,
        )
        app = create_app(config)
        if not hasattr(app.state, "tool_registry"):
            app.state.tool_registry = ToolRegistry.from_directory(temp_tools_dir)
        local_client = TestClient(app)

        response = local_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["api_key_configured"] is False

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AgentIR Workflow Generator"
        assert "docs" in data


# ---- Test: Workflow Generate (Happy Path) ----

class TestWorkflowGenerateSuccess:
    def test_generate_successful_workflow(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research then write a report."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["workflow_id"] != ""
        assert data["workflow_id"].startswith("wf_")
        assert data["plan_result"]["success"] is True
        assert data["plan_result"]["workflow_name"] == "test_workflow"
        assert data["agentir_json"] is not None
        assert data["agentir_json"]["name"] == "test_workflow"
        assert data["validation_report"]["is_valid"] is True
        assert data["adk_source_code"] is not None
        assert "START" in data["adk_source_code"]
        assert data["elapsed_ms"] >= 0

    def test_generate_saves_artifact_files(self, client, mock_planner_success, temp_artifacts_dir):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research then write a report."},
        )
        data = response.json()
        wf_id = data["workflow_id"]
        assert wf_id != ""

        # Check files exist on disk
        req_file = temp_artifacts_dir / "requirements" / f"{wf_id}.txt"
        src_file = temp_artifacts_dir / "outputs" / f"{wf_id}.py"
        index_file = temp_artifacts_dir / "index.json"

        assert req_file.is_file(), f"Missing {req_file}"
        assert src_file.is_file(), f"Missing {src_file}"
        assert index_file.is_file(), f"Missing {index_file}"

        # Verify file contents
        assert "Research then write a report." in req_file.read_text()
        assert "LlmAgent" in src_file.read_text()

    def test_generate_with_options(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={
                "requirement": "Research then write.",
                "options": {
                    "model": "deepseek-reasoner",
                    "temperature": 0.3,
                    "max_retries": 2,
                    "agent_overrides": [
                        {
                            "agent_name": "researcher",
                            "model": "custom-model",
                            "instruction": "You are a specialist.",
                            "temperature": 0.1,
                        },
                    ],
                },
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["adk_source_code"] is not None

    def test_generate_returns_valid_python(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "A researcher agent."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        compile(data["adk_source_code"], "<generated>", "exec")

    def test_generate_returns_agentir_json(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research then review."},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["agentir_json"], dict)
        assert "name" in data["agentir_json"]
        assert "root" in data["agentir_json"]

    def test_generate_includes_elapsed_time(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "A simple workflow."},
        )
        assert response.status_code == 200
        data = response.json()
        assert "elapsed_ms" in data
        assert data["elapsed_ms"] >= 0


# ---- Test: Workflow Generate (Failure Paths) ----

class TestWorkflowGenerateFailure:
    def test_planner_failure(self, client, mock_planner_failure):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Some impossible workflow description."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["plan_result"]["success"] is False
        assert data["plan_result"]["retries"] == 3
        assert len(data["plan_result"]["errors"]) >= 1
        assert data["adk_source_code"] is None
        # workflow_id should be empty on failure
        assert data["workflow_id"] == ""

    def test_empty_requirement_rejected(self, client):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": ""},
        )
        assert response.status_code == 422

    def test_missing_requirement_rejected(self, client):
        response = client.post(
            "/api/v1/workflows/generate",
            json={},
        )
        assert response.status_code == 422

    def test_invalid_temperature_rejected(self, client):
        response = client.post(
            "/api/v1/workflows/generate",
            json={
                "requirement": "test",
                "options": {"temperature": 3.0},
            },
        )
        assert response.status_code == 422

    def test_negative_max_retries_rejected(self, client):
        response = client.post(
            "/api/v1/workflows/generate",
            json={
                "requirement": "test",
                "options": {"max_retries": -1},
            },
        )
        assert response.status_code == 422


# ---- Test: Workflow Data — Verify Generated Content ----

class TestGeneratedWorkflowContent:
    def test_adk_contains_agent_definitions(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research then write."},
        )
        data = response.json()
        code = data["adk_source_code"]
        assert "researcher" in code
        assert "writer" in code
        assert "LlmAgent" in code
        assert "Workflow" in code

    def test_adk_contains_imports(self, client, mock_planner_success):
        response = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research and publish."},
        )
        code = response.json()["adk_source_code"]
        assert "from google.adk.agents" in code
        assert "from google.adk.workflow" in code


# ---- Test: List Workflows ----

class TestWorkflowList:
    def test_list_empty(self, client):
        response = client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_after_generate(self, client, mock_planner_success):
        # Generate a workflow first
        r1 = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research then write."},
        )
        wf1_id = r1.json()["workflow_id"]

        r2 = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Translate to English."},
        )
        wf2_id = r2.json()["workflow_id"]

        # List
        response = client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

        # Newest first
        assert data["items"][0]["workflow_id"] == wf2_id
        assert data["items"][1]["workflow_id"] == wf1_id

        # Check fields
        item = data["items"][0]
        assert item["name"] == "test_workflow"
        assert item["status"] == "generated"
        assert item["created_at"] != ""

    def test_list_pagination(self, client, mock_planner_success):
        # Generate 3 workflows
        for i in range(3):
            client.post(
                "/api/v1/workflows/generate",
                json={"requirement": f"Workflow {i}."},
            )

        # Page 1: limit=2
        r = client.get("/api/v1/workflows?limit=2&offset=0")
        data = r.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2

        # Page 2
        r = client.get("/api/v1/workflows?limit=2&offset=2")
        data = r.json()
        assert data["total"] == 3
        assert len(data["items"]) == 1

    def test_list_shows_requirement(self, client, mock_planner_success):
        client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "My custom 多语言 workflow."},
        )
        r = client.get("/api/v1/workflows")
        items = r.json()["items"]
        assert "My custom 多语言 workflow." in items[0]["requirement"]


# ---- Test: Run Workflow ----

class TestWorkflowRun:
    def test_run_not_found(self, client):
        response = client.post(
            "/api/v1/workflows/nonexistent_wf_id/run",
            json={"input_text": "hello"},
        )
        assert response.status_code == 404

    def test_run_generated_workflow(self, client, mock_planner_success, temp_artifacts_dir):
        # Generate
        gen_resp = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "A simple research workflow."},
        )
        wf_id = gen_resp.json()["workflow_id"]

        # Run
        response = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            json={"input_text": "Analyze this data.", "timeout_seconds": 30},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == wf_id
        assert "exit_code" in data
        assert "stdout" in data
        assert "stderr" in data

        # The generated script likely won't actually run (no google.adk installed),
        # but the runner should capture the error gracefully
        assert "log_path" in data
        assert data["log_path"] != ""

        # Check log file exists
        log_full_path = temp_artifacts_dir / data["log_path"]
        assert log_full_path.is_file(), f"Log file missing: {log_full_path}"
        log_content = log_full_path.read_text()
        assert "Workflow ID" in log_content
        assert wf_id in log_content

    def test_run_updates_status(self, client, mock_planner_success, temp_artifacts_dir):
        # Generate
        gen_resp = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "Research workflow."},
        )
        wf_id = gen_resp.json()["workflow_id"]

        # Run
        client.post(
            f"/api/v1/workflows/{wf_id}/run",
            json={"timeout_seconds": 30},
        )

        # Check status in list
        r = client.get("/api/v1/workflows")
        items = r.json()["items"]
        item = next(i for i in items if i["workflow_id"] == wf_id)
        # Status should be updated (completed or failed depending on env)
        assert item["status"] in ("completed", "failed")

    def test_run_without_input(self, client, mock_planner_success):
        gen_resp = client.post(
            "/api/v1/workflows/generate",
            json={"requirement": "A simple workflow."},
        )
        wf_id = gen_resp.json()["workflow_id"]

        # Run without input_text
        response = client.post(
            f"/api/v1/workflows/{wf_id}/run",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == wf_id


# ---- Test: Artifact Store ----

class TestArtifactStore:
    def test_save_and_list(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)

        record = store.save_workflow(
            requirement="Test requirement.",
            source_code="print('hello')",
            name="test_wf",
            description="A test",
            elapsed_ms=100.0,
        )

        assert record.workflow_id.startswith("wf_")
        assert record.name == "test_wf"

        records, total = store.list_workflows()
        assert total == 1
        assert records[0].workflow_id == record.workflow_id

    def test_get_workflow(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        record = store.save_workflow(
            requirement="Req",
            source_code="print('x')",
            name="wf1",
        )

        found = store.get_workflow(record.workflow_id)
        assert found is not None
        assert found.workflow_id == record.workflow_id
        assert found.name == "wf1"

    def test_get_nonexistent(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        assert store.get_workflow("nonexistent") is None

    def test_update_status(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        record = store.save_workflow(
            requirement="Req",
            source_code="print('x')",
            name="wf1",
        )

        updated = store.update_status(record.workflow_id, status="completed")
        assert updated is not None
        assert updated.status == "completed"

        # Verify persistence
        found = store.get_workflow(record.workflow_id)
        assert found is not None
        assert found.status == "completed"

    def test_update_status_with_error(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        record = store.save_workflow(
            requirement="Req",
            source_code="print('x')",
            name="wf1",
        )

        updated = store.update_status(
            record.workflow_id,
            status="failed",
            error="ImportError: no module named foo",
        )
        assert updated.error == "ImportError: no module named foo"

    def test_list_pagination(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        for i in range(5):
            store.save_workflow(
                requirement=f"Req {i}",
                source_code=f"print({i})",
                name=f"wf_{i}",
            )

        page, total = store.list_workflows(offset=0, limit=3)
        assert total == 5
        assert len(page) == 3

        page2, _ = store.list_workflows(offset=3, limit=3)
        assert len(page2) == 2

    def test_source_path(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        record = store.save_workflow(
            requirement="Req",
            source_code="print('hello')",
        )

        path = store.get_source_path(record.workflow_id)
        assert path is not None
        assert path.is_file()
        assert path.read_text() == "print('hello')"

    def test_source_path_nonexistent(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        assert store.get_source_path("nonexistent") is None

    def test_files_persisted(self, temp_artifacts_dir):
        from agentir.artifacts.store import WorkflowArtifactStore

        store = WorkflowArtifactStore(temp_artifacts_dir)
        record = store.save_workflow(
            requirement="Save me",
            source_code="print('persisted')",
            name="persist_test",
        )

        req_file = temp_artifacts_dir / "requirements" / f"{record.workflow_id}.txt"
        src_file = temp_artifacts_dir / "outputs" / f"{record.workflow_id}.py"
        index_file = temp_artifacts_dir / "index.json"

        assert req_file.is_file()
        assert src_file.is_file()
        assert index_file.is_file()
        assert req_file.read_text() == "Save me"
        assert src_file.read_text() == "print('persisted')"


# ---- Test: Workflow Runner ----

class TestWorkflowRunner:
    def test_run_simple_script(self, temp_artifacts_dir):
        from agentir.artifacts.runner import WorkflowRunner

        # Create a simple Python script
        script = temp_artifacts_dir / "test_script.py"
        script.write_text(
            "import sys\n"
            "print('Hello from workflow')\n"
            "input_data = sys.stdin.read().strip()\n"
            "print(f'Received: {input_data}')\n"
        )

        logs_dir = temp_artifacts_dir / "logs"
        runner = WorkflowRunner(logs_dir=logs_dir)
        result = runner.run(
            workflow_id="wf_test",
            script_path=script,
            input_text="Hello World",
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.exit_code == 0
        assert "Hello from workflow" in result.stdout
        assert "Received: Hello World" in result.stdout
        assert result.log_path != ""
        assert Path(result.log_path).is_file()

        # Verify log content
        log_text = Path(result.log_path).read_text()
        assert "wf_test" in log_text
        assert "Hello from workflow" in log_text
        assert "EXIT CODE: 0" in log_text

    def test_run_failing_script(self, temp_artifacts_dir):
        from agentir.artifacts.runner import WorkflowRunner

        script = temp_artifacts_dir / "fail_script.py"
        script.write_text("import sys; sys.exit(1)\n")

        runner = WorkflowRunner(logs_dir=temp_artifacts_dir / "logs")
        result = runner.run(
            workflow_id="wf_fail",
            script_path=script,
            timeout_seconds=10,
        )

        assert result.success is False
        assert result.exit_code == 1

    def test_run_missing_script(self, temp_artifacts_dir):
        from agentir.artifacts.runner import WorkflowRunner

        runner = WorkflowRunner(logs_dir=temp_artifacts_dir / "logs")
        result = runner.run(
            workflow_id="wf_missing",
            script_path=temp_artifacts_dir / "nonexistent.py",
        )

        assert result.success is False
        assert len(result.errors) > 0
        assert "Script not found" in result.errors[0]

    def test_run_timeout(self, temp_artifacts_dir):
        from agentir.artifacts.runner import WorkflowRunner

        script = temp_artifacts_dir / "slow_script.py"
        script.write_text("import time; time.sleep(10)\n")

        runner = WorkflowRunner(logs_dir=temp_artifacts_dir / "logs")
        result = runner.run(
            workflow_id="wf_slow",
            script_path=script,
            timeout_seconds=1,
        )

        assert result.success is False
        assert "timed out" in result.errors[0].lower()

    def test_run_writes_log_file(self, temp_artifacts_dir):
        from agentir.artifacts.runner import WorkflowRunner

        script = temp_artifacts_dir / "hello.py"
        script.write_text("print('log me')\n")

        logs_dir = temp_artifacts_dir / "logs"
        runner = WorkflowRunner(logs_dir=logs_dir)
        result = runner.run(
            workflow_id="wf_log_test",
            script_path=script,
        )

        log_path = Path(result.log_path)
        assert log_path.is_file()
        content = log_path.read_text()
        assert "wf_log_test" in content
        assert "log me" in content
        assert "EXIT CODE: 0" in content


# ---- Test: Request/Response Model Serialization ----

class TestModels:
    def test_workflow_generate_request_serialization(self):
        from agentir.server.models import (
            WorkflowGenerateRequest,
            WorkflowGenerateOptions,
            AgentConfigOverride,
        )

        req = WorkflowGenerateRequest(
            requirement="Test workflow.",
            options=WorkflowGenerateOptions(
                model="deepseek-chat",
                temperature=0.5,
                agent_overrides=[
                    AgentConfigOverride(
                        agent_name="researcher",
                        model="deepseek-reasoner",
                        instruction="You are a researcher.",
                    ),
                ],
            ),
        )

        json_str = req.model_dump_json()
        parsed = WorkflowGenerateRequest.model_validate_json(json_str)
        assert parsed.requirement == "Test workflow."
        assert parsed.options.model == "deepseek-chat"
        assert parsed.options.agent_overrides[0].agent_name == "researcher"

    def test_workflow_generate_response_serialization(self):
        from agentir.server.models import (
            PlanResultInfo,
            ValidationReportInfo,
            WorkflowGenerateResponse,
        )

        resp = WorkflowGenerateResponse(
            workflow_id="wf_20250616_abc123",
            success=True,
            plan_result=PlanResultInfo(
                success=True,
                workflow_name="test",
                workflow_version="0.1.0",
                workflow_description="A test",
                retries=0,
            ),
            agentir_json={"name": "test", "root": {"type": "agent", "agent": "x"}},
            validation_report=ValidationReportInfo(is_valid=True),
            adk_source_code="# Python code",
            elapsed_ms=42.5,
        )

        json_str = resp.model_dump_json()
        parsed = WorkflowGenerateResponse.model_validate_json(json_str)
        assert parsed.workflow_id == "wf_20250616_abc123"
        assert parsed.success is True
        assert parsed.adk_source_code == "# Python code"
        assert parsed.elapsed_ms == 42.5

    def test_health_response(self):
        from agentir.server.models import HealthResponse

        resp = HealthResponse(
            status="ok",
            version="0.1.0",
            provider="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key_configured=True,
            artifacts_dir="/tmp/artifacts",
        )
        data = resp.model_dump_json()
        parsed = HealthResponse.model_validate_json(data)
        assert parsed.provider == "deepseek"
        assert parsed.artifacts_dir == "/tmp/artifacts"

    def test_workflow_list_item(self):
        from agentir.server.models import WorkflowListItem

        item = WorkflowListItem(
            workflow_id="wf_test_123",
            name="My Workflow",
            description="A test",
            requirement="Do something.",
            created_at="2025-01-01T00:00:00+00:00",
            status="generated",
            elapsed_ms=100.0,
        )
        json_str = item.model_dump_json()
        parsed = WorkflowListItem.model_validate_json(json_str)
        assert parsed.workflow_id == "wf_test_123"
        assert parsed.status == "generated"

    def test_workflow_list_response(self):
        from agentir.server.models import WorkflowListItem, WorkflowListResponse

        resp = WorkflowListResponse(
            total=2,
            offset=0,
            limit=20,
            items=[
                WorkflowListItem(workflow_id="wf_1"),
                WorkflowListItem(workflow_id="wf_2"),
            ],
        )
        json_str = resp.model_dump_json()
        parsed = WorkflowListResponse.model_validate_json(json_str)
        assert parsed.total == 2
        assert len(parsed.items) == 2

    def test_workflow_run_request(self):
        from agentir.server.models import WorkflowRunRequest

        req = WorkflowRunRequest(input_text="Analyze this.", timeout_seconds=60)
        json_str = req.model_dump_json()
        parsed = WorkflowRunRequest.model_validate_json(json_str)
        assert parsed.input_text == "Analyze this."
        assert parsed.timeout_seconds == 60

    def test_workflow_run_request_defaults(self):
        from agentir.server.models import WorkflowRunRequest

        req = WorkflowRunRequest()
        assert req.input_text == ""
        assert req.timeout_seconds == 300

    def test_workflow_run_response(self):
        from agentir.server.models import WorkflowRunResponse

        resp = WorkflowRunResponse(
            success=True,
            workflow_id="wf_123",
            exit_code=0,
            stdout="Done!",
            stderr="",
            log_path="logs/wf_123_20250101.log",
            started_at="2025-01-01T00:00:00+00:00",
            finished_at="2025-01-01T00:00:01+00:00",
            elapsed_ms=1000.0,
        )
        json_str = resp.model_dump_json()
        parsed = WorkflowRunResponse.model_validate_json(json_str)
        assert parsed.success is True
        assert parsed.exit_code == 0


# ---- Test: API Docs ----

class TestOpenAPI:
    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema["paths"]
        # Existing endpoints
        assert "/api/v1/health" in paths
        assert "/api/v1/workflows/generate" in paths
        # New endpoints
        assert "/api/v1/workflows" in paths
        assert "/api/v1/workflows/{workflow_id}/run" in paths
        assert "get" in paths["/api/v1/health"]
        assert "post" in paths["/api/v1/workflows/generate"]
        assert "get" in paths["/api/v1/workflows"]
        assert "post" in paths["/api/v1/workflows/{workflow_id}/run"]

        # Verify the POST request schema
        post_spec = paths["/api/v1/workflows/generate"]["post"]
        assert "requestBody" in post_spec
        assert "responses" in post_spec
        assert "200" in post_spec["responses"]

    def test_docs_page_accessible(self, client):
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_redoc_page_accessible(self, client):
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# ---- Test: ServerConfig ----

class TestServerConfig:
    def test_from_env_basic(self, mock_llm_env):
        from agentir.server.config import ServerConfig

        config = ServerConfig.from_env()
        assert config.llm.provider == "deepseek"
        assert config.llm.model == "deepseek-chat"
        assert config.host == "0.0.0.0"
        assert config.port == 8000

    def test_from_env_custom_port(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AGENTIR_PORT", "9000")

        from agentir.server.config import ServerConfig

        config = ServerConfig.from_env()
        assert config.port == 9000

    def test_from_env_custom_artifacts_dir(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "openai")
        monkeypatch.setenv("AGENTIR_ARTIFACTS_DIR", "/custom/artifacts")

        from agentir.server.config import ServerConfig

        config = ServerConfig.from_env()
        assert str(config.artifacts_dir) == "/custom/artifacts"

    def test_is_ready_true(self, mock_llm_env):
        from agentir.server.config import ServerConfig

        config = ServerConfig.from_env()
        assert config.is_ready() is True

    def test_is_ready_false_when_no_model(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "custom")
        monkeypatch.setenv("AGENTIR_LLM_MODEL", "")

        from agentir.server.config import ServerConfig

        config = ServerConfig.from_env()
        assert config.is_ready() is False or config.llm.base_url == ""


# ---- Test: CLI Module ----

class TestCLI:
    def test_cli_module_imports(self):
        from agentir.server import cli

        assert cli.main is not None

    def test_entry_point_defined(self):
        from agentir.server.cli import main

        assert callable(main)
