"""Tests for the Planner module."""

import json

import pytest

from agentir.planner.planner import (
    DEFAULT_MAX_RETRIES,
    Planner,
    PlanResult,
    _SYSTEM_PROMPT,
    _USER_PROMPT_TEMPLATE,
    _ERROR_PROMPT_TEMPLATE,
)
from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import AgentNode, ConditionNode, SequenceNode


# ---- Mock helpers ----

def _make_mock_llm(response: str):
    """Create a callable that returns a fixed response."""
    return lambda prompt: response


def _make_call_counter_llm(responses: list[str]):
    """Create a callable that returns responses in sequence."""
    counter = [0]

    def call(prompt: str) -> str:
        idx = counter[0]
        counter[0] += 1
        return responses[min(idx, len(responses) - 1)]

    return call


# ---- Test: PlanResult ----

class TestPlanResult:
    def test_success_result(self):
        wf = WorkflowDefinition(
            name="test",
            root=AgentNode(agent="worker"),
        )
        result = PlanResult(workflow=wf, success=True, raw_response="{}", retries=0)
        assert result.success
        assert result.workflow is not None
        assert result.workflow.name == "test"

    def test_failure_result(self):
        result = PlanResult(
            success=False,
            errors=["Something went wrong"],
            retries=3,
        )
        assert not result.success
        assert result.workflow is None
        assert len(result.errors) == 1
        assert result.retries == 3
        assert result.to_dict() is None
        assert result.to_json() is None

    def test_to_dict(self):
        wf = WorkflowDefinition(
            name="test",
            root=AgentNode(agent="worker"),
        )
        result = PlanResult(workflow=wf, success=True)
        d = result.to_dict()
        assert d is not None
        assert d["name"] == "test"

    def test_to_json(self):
        wf = WorkflowDefinition(
            name="test",
            root=AgentNode(agent="worker"),
        )
        result = PlanResult(workflow=wf, success=True)
        j = result.to_json()
        assert j is not None
        data = json.loads(j)
        assert data["name"] == "test"


# ---- Test: Planner - Simple agent workflow ----

class TestPlannerSimpleAgent:
    def test_plan_single_agent(self):
        response = json.dumps({
            "name": "simple_agent",
            "version": "0.1.0",
            "description": "A single agent workflow",
            "root": {"type": "agent", "agent": "assistant"},
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan("An assistant agent")

        assert result.success
        assert result.workflow is not None
        assert result.workflow.name == "simple_agent"
        assert isinstance(result.workflow.root, AgentNode)
        assert result.workflow.root.agent == "assistant"
        assert result.retries == 0

    def test_plan_agent_sequence(self):
        response = json.dumps({
            "name": "research_pipeline",
            "version": "0.1.0",
            "description": "Research then write",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "researcher"},
                    {"type": "agent", "agent": "writer"},
                ],
            },
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan("Research then write")

        assert result.success
        assert result.workflow is not None
        root = result.workflow.root
        assert isinstance(root, SequenceNode)
        assert len(root.steps) == 2
        assert root.steps[0].agent == "researcher"
        assert root.steps[1].agent == "writer"


# ---- Test: Planner - Condition ----

class TestPlannerCondition:
    def test_plan_simple_condition(self):
        response = json.dumps({
            "name": "conditional_pipeline",
            "version": "0.1.0",
            "description": "Conditional branching",
            "root": {
                "type": "condition",
                "expression": "output.quality > 0.8",
                "true_branch": {"type": "agent", "agent": "publisher"},
                "false_branch": {"type": "agent", "agent": "reviser"},
            },
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan("If quality is high publish, else revise")

        assert result.success
        root = result.workflow.root
        assert isinstance(root, ConditionNode)
        assert root.expression == "output.quality > 0.8"
        assert root.true_branch.agent == "publisher"
        assert root.false_branch.agent == "reviser"


# ---- Test: Planner - Loop ----

class TestPlannerLoop:
    def test_plan_simple_loop(self):
        response = json.dumps({
            "name": "review_loop",
            "version": "0.1.0",
            "description": "Review loop with retry",
            "root": {
                "type": "loop",
                "max_iterations": 3,
                "body": {"type": "agent", "agent": "reviewer"},
            },
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan("Review up to 3 times")

        assert result.success
        from agentir.ir.nodes import LoopNode

        root = result.workflow.root
        assert isinstance(root, LoopNode)
        assert root.max_iterations == 3
        assert root.body.agent == "reviewer"


# ---- Test: Planner - Parallel ----

class TestPlannerParallel:
    def test_plan_parallel_branches(self):
        response = json.dumps({
            "name": "parallel_translate",
            "version": "0.1.0",
            "description": "Translate in parallel",
            "root": {
                "type": "parallel",
                "branches": [
                    {"type": "agent", "agent": "translator_en"},
                    {"type": "agent", "agent": "translator_zh"},
                ],
            },
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan("Translate to English and Chinese in parallel")

        assert result.success
        from agentir.ir.nodes import ParallelNode

        root = result.workflow.root
        assert isinstance(root, ParallelNode)
        assert len(root.branches) == 2


# ---- Test: Planner - Complex nested workflow ----

class TestPlannerComplexNested:
    def test_plan_sequence_with_condition_and_loop(self):
        response = json.dumps({
            "name": "quality_pipeline",
            "version": "0.1.0",
            "description": "Generate content with quality check loop",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "generator"},
                    {
                        "type": "loop",
                        "max_iterations": 5,
                        "body": {
                            "type": "sequence",
                            "steps": [
                                {"type": "agent", "agent": "checker"},
                                {
                                    "type": "condition",
                                    "expression": "output.score >= 0.8",
                                    "true_branch": {"type": "agent", "agent": "finalizer"},
                                    "false_branch": {"type": "agent", "agent": "improver"},
                                },
                            ],
                        },
                    },
                ],
            },
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan(
            "Generate content, then check quality up to 5 times. "
            "If score is good, finalize; otherwise improve."
        )

        assert result.success
        root = result.workflow.root
        assert isinstance(root, SequenceNode)
        assert len(root.steps) == 2
        assert root.steps[0].agent == "generator"

        from agentir.ir.nodes import LoopNode

        loop = root.steps[1]
        assert isinstance(loop, LoopNode)
        assert loop.max_iterations == 5

        body = loop.body
        assert isinstance(body, SequenceNode)
        assert len(body.steps) == 2
        assert body.steps[0].agent == "checker"
        assert body.steps[1].expression == "output.score >= 0.8"


# ---- Test: Planner - plan_with_context ----

class TestPlannerWithContext:
    def test_plan_with_available_agents(self):
        response = json.dumps({
            "name": "agent_pipe",
            "version": "0.1.0",
            "description": "Use available agents",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "researcher"},
                    {"type": "agent", "agent": "writer"},
                ],
            },
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan_with_context(
            "Research and write",
            available_agents=["researcher", "writer", "reviewer"],
        )

        assert result.success
        root = result.workflow.root
        assert isinstance(root, SequenceNode)
        assert root.steps[0].agent == "researcher"
        assert root.steps[1].agent == "writer"


# ---- Test: Planner - Prompt construction ----

class TestPlannerPrompt:
    def test_build_prompt_includes_system_and_user(self):
        def dummy_llm(prompt: str) -> str:
            # System prompt is formatted with tool_context, so check for key content
            assert "AgentIR Schema" in prompt
            assert "make a tea" in prompt
            return json.dumps({
                "name": "tea",
                "root": {"type": "agent", "agent": "brewer"},
            })

        planner = Planner(llm_callable=dummy_llm)
        result = planner.plan("make a tea")
        assert result.success

    def test_error_prompt_contains_errors(self):
        """Ensure error retry prompt includes validation errors."""
        planner = Planner(llm_callable=_make_mock_llm(""))
        prompt = planner._build_error_prompt(
            "bad json", ["Missing field 'name'", "Invalid root type"]
        )
        assert "Missing field 'name'" in prompt
        assert "Invalid root type" in prompt
        assert "bad json" in prompt


# ---- Test: JSON Extraction ----

class TestJsonExtraction:
    def test_extract_clean_json(self):
        text = '{"name": "test", "root": {"type": "agent", "agent": "w"}}'
        result = Planner._extract_json(text)
        assert result["name"] == "test"

    def test_extract_from_markdown_fence(self):
        text = """\
Here is the workflow:
```json
{"name": "test", "root": {"type": "agent", "agent": "w"}}
```
Done."""
        result = Planner._extract_json(text)
        assert result["name"] == "test"

    def test_extract_from_markdown_fence_no_language(self):
        text = """\
```
{"name": "test", "root": {"type": "agent", "agent": "w"}}
```"""
        result = Planner._extract_json(text)
        assert result["name"] == "test"

    def test_extract_json_with_extra_text(self):
        text = 'Sure! Here is the JSON: {"name": "test", "root": {"type": "agent", "agent": "w"}} Hope that helps!'
        result = Planner._extract_json(text)
        assert result["name"] == "test"

    def test_extract_nested_braces(self):
        text = json.dumps({
            "name": "test",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "a"},
                    {"type": "agent", "agent": "b"},
                ],
            },
        })
        result = Planner._extract_json(text)
        assert result["name"] == "test"
        assert len(result["root"]["steps"]) == 2

    def test_extract_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            Planner._extract_json("Just some text, no JSON here")


# ---- Test: Retry on validation error ----

class TestPlannerRetry:
    def test_retry_on_validation_error_then_succeed(self):
        bad_response = json.dumps({
            "name": "bad",
            "root": {"type": "sequence", "steps": []},  # empty sequence
        })
        good_response = json.dumps({
            "name": "good",
            "version": "0.1.0",
            "description": "Fixed workflow",
            "root": {
                "type": "sequence",
                "steps": [{"type": "agent", "agent": "worker"}],
            },
        })
        planner = Planner(
            llm_callable=_make_call_counter_llm([bad_response, good_response]),
            max_retries=3,
        )
        result = planner.plan("A worker agent")

        assert result.success
        assert result.workflow is not None
        assert result.workflow.name == "good"
        assert result.retries == 1  # 1 retry needed

    def test_retry_on_parse_error_then_succeed(self):
        bad_response = "This is not JSON"
        good_response = json.dumps({
            "name": "good",
            "root": {"type": "agent", "agent": "worker"},
        })
        planner = Planner(
            llm_callable=_make_call_counter_llm([bad_response, good_response]),
            max_retries=3,
        )
        result = planner.plan("A worker agent")

        assert result.success
        assert result.workflow is not None
        assert result.retries == 1

    def test_max_retries_exhausted(self):
        bad_response = json.dumps({
            "name": "bad",
            "root": {"type": "sequence", "steps": []},  # always invalid
        })
        planner = Planner(
            llm_callable=_make_mock_llm(bad_response),
            max_retries=2,
        )
        result = planner.plan("A sequence workflow")

        assert not result.success
        assert result.workflow is None
        assert result.retries == 2
        assert len(result.errors) > 0

    def test_parse_error_max_retries_exhausted(self):
        planner = Planner(
            llm_callable=_make_mock_llm("Not JSON at all"),
            max_retries=2,
        )
        result = planner.plan("A workflow")

        assert not result.success
        assert result.workflow is None
        assert len(result.errors) > 0

    def test_llm_call_exception(self):
        def failing_llm(prompt: str) -> str:
            raise RuntimeError("API unavailable")

        planner = Planner(llm_callable=failing_llm, max_retries=2)
        result = planner.plan("A workflow")

        assert not result.success
        assert "API unavailable" in result.errors[0]

    def test_empty_response(self):
        planner = Planner(llm_callable=_make_mock_llm("   "), max_retries=2)
        result = planner.plan("A workflow")

        assert not result.success
        assert any("empty" in e.lower() for e in result.errors)


# ---- Test: Full pipeline integration (Planner → Validator → Compiler) ----

class TestFullPipelineIntegration:
    def test_nl_to_compiler_roundtrip(self):
        """End-to-end: NL → Planner → AgentIR → Validator → ADK Compiler → valid Python."""
        from agentir.compiler.adk import ADKCompiler

        response = json.dumps({
            "name": "full_pipeline_test",
            "version": "0.1.0",
            "description": "Test the full pipeline",
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

        # Step 1: NL → Planner (mocked LLM gives us AgentIR JSON)
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan(
            "Research, then if needs review loop with reviewer up to 3 times, "
            "otherwise write. Finally publish."
        )
        assert result.success

        # Step 2: Validate (implicit in planner, but explicit here for demo)
        from agentir.validator import validate_workflow

        report = validate_workflow(result.workflow)
        assert report.is_valid

        # Step 3: Compile to ADK
        compiler_result = ADKCompiler().compile(result.workflow)
        assert compiler_result.success

        # Step 4: Verify valid Python
        compile(compiler_result.source_code, "<generated>", "exec")
        assert "researcher" in compiler_result.source_code
        assert "reviewer" in compiler_result.source_code
        assert "writer" in compiler_result.source_code
        assert "publisher" in compiler_result.source_code


# ---- Test: Default max_retries ----

class TestPlannerDefaults:
    def test_default_max_retries(self):
        def dummy(prompt: str) -> str:
            return json.dumps({
                "name": "d",
                "root": {"type": "agent", "agent": "x"},
            })

        planner = Planner(llm_callable=dummy)
        assert planner.max_retries == DEFAULT_MAX_RETRIES


# ---- Test: Planner with LLMConfig (new API) ----

class TestPlannerWithLLMConfig:
    """Test Planner using the new llm_config parameter."""

    def test_planner_with_llmconfig_deepseek(self, monkeypatch):
        """Planner created via llm_config=LLMConfig.deepseek(...) should work."""
        from agentir.llm.config import LLMConfig

        response = json.dumps({
            "name": "deepseek_workflow",
            "version": "0.1.0",
            "description": "Generated via DeepSeek",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "researcher"},
                    {"type": "agent", "agent": "writer"},
                ],
            },
        })

        # Mock create_llm_callable to return a simple mock
        monkeypatch.setattr(
            "agentir.planner.planner.create_llm_callable",
            lambda config: _make_mock_llm(response),
        )

        config = LLMConfig.deepseek(api_key="sk-test", model="deepseek-chat")
        planner = Planner(llm_config=config, max_retries=1)
        result = planner.plan("Research then write")
        assert result.success
        assert result.workflow.name == "deepseek_workflow"

    def test_planner_with_llmconfig_openai(self, monkeypatch):
        """Planner via LLMConfig.openai() should work."""
        from agentir.llm.config import LLMConfig

        response = json.dumps({
            "name": "openai_workflow",
            "root": {"type": "agent", "agent": "assistant"},
        })
        monkeypatch.setattr(
            "agentir.planner.planner.create_llm_callable",
            lambda config: _make_mock_llm(response),
        )

        config = LLMConfig.openai(api_key="sk-test")
        planner = Planner(llm_config=config, max_retries=1)
        result = planner.plan("An assistant")
        assert result.success

    def test_planner_with_llmconfig_custom(self, monkeypatch):
        """Planner via LLMConfig.custom() should work."""
        from agentir.llm.config import LLMConfig

        response = json.dumps({
            "name": "custom_workflow",
            "root": {"type": "agent", "agent": "worker"},
        })
        monkeypatch.setattr(
            "agentir.planner.planner.create_llm_callable",
            lambda config: _make_mock_llm(response),
        )

        config = LLMConfig.custom(
            base_url="http://localhost:8000/v1",
            model="local-model",
            api_key="local-key",
        )
        planner = Planner(llm_config=config, max_retries=1)
        result = planner.plan("A worker")
        assert result.success

    def test_planner_no_config_or_callable_raises(self):
        """Planner() without llm_config or llm_callable should raise ValueError."""
        with pytest.raises(ValueError, match="Either llm_config or llm_callable"):
            Planner()

    def test_llm_callable_still_works(self):
        """Backward compatibility: Planner(llm_callable=...) still works."""
        response = json.dumps({
            "name": "old_api",
            "root": {"type": "agent", "agent": "legacy"},
        })
        planner = Planner(llm_callable=_make_mock_llm(response))
        result = planner.plan("Legacy")
        assert result.success
        assert result.workflow.name == "old_api"


# ---- Test: Planner + LLMConfig end-to-end with retry ----

class TestPlannerWithLLMConfigRetry:
    def test_retry_with_llmconfig(self, monkeypatch):
        """Retry loop should work with llm_config-based Planner."""
        from agentir.llm.config import LLMConfig

        good_response = json.dumps({
            "name": "after_retry",
            "root": {"type": "agent", "agent": "worker"},
        })

        monkeypatch.setattr(
            "agentir.planner.planner.create_llm_callable",
            lambda config: _make_call_counter_llm([
                "not json",  # 1st: parse error
                json.dumps({  # 2nd: invalid (empty sequence)
                    "name": "bad",
                    "root": {"type": "sequence", "steps": []},
                }),
                good_response,  # 3rd: success
            ]),
        )

        config = LLMConfig.deepseek(api_key="sk-test")
        planner = Planner(llm_config=config, max_retries=3)
        result = planner.plan("A worker agent")
        assert result.success
        assert result.workflow.name == "after_retry"
        assert result.retries == 2
