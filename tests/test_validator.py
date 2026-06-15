"""Tests for the AgentIR Validator."""

import pytest

from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import (
    AgentNode,
    ConditionNode,
    LoopNode,
    ParallelNode,
    SequenceNode,
)
from agentir.validator.rules import AgentRegistry, ValidationError
from agentir.validator.validator import (
    ValidationReport,
    validate_workflow,
    validate_workflow_dict,
    validate_workflow_json,
)


class TestValidationReport:
    def test_valid_report(self):
        report = ValidationReport(is_valid=True)
        assert report.is_valid
        assert report.errors == []
        assert "valid" in report.summary()

    def test_invalid_report(self):
        report = ValidationReport(
            is_valid=False,
            errors=[ValidationError(code="E001", message="test error", path="root")]
        )
        assert not report.is_valid
        assert "test error" in report.summary()
        assert "E001" in report.summary()


class TestAgentExistence:
    def test_all_agents_found(self):
        wf = WorkflowDefinition(
            name="test",
            root=SequenceNode(steps=[
                AgentNode(agent="researcher"),
                AgentNode(agent="writer"),
            ]),
        )
        registry = AgentRegistry.from_list(["researcher", "writer"])
        report = validate_workflow(wf, agent_registry=registry)
        assert report.is_valid

    def test_missing_agent(self):
        wf = WorkflowDefinition(
            name="test",
            root=AgentNode(agent="unknown_agent"),
        )
        registry = AgentRegistry.from_list(["researcher"])
        report = validate_workflow(wf, agent_registry=registry)
        assert not report.is_valid
        assert any("unknown_agent" in e.message for e in report.errors)
        assert any(e.code == "AGENT_NOT_FOUND" for e in report.errors)

    def test_missing_agent_in_nested_structure(self):
        wf = WorkflowDefinition(
            name="test",
            root=ConditionNode(
                expression="x",
                true_branch=AgentNode(agent="exists"),
                false_branch=AgentNode(agent="missing"),
            ),
        )
        registry = AgentRegistry.from_list(["exists"])
        report = validate_workflow(wf, agent_registry=registry)
        assert not report.is_valid
        assert any("missing" in e.message for e in report.errors)
        # Check path includes false_branch
        assert any("false_branch" in e.path for e in report.errors)

    def test_without_registry_passes(self):
        """Agent existence check is skipped if no registry provided."""
        wf = WorkflowDefinition(
            name="test",
            root=AgentNode(agent="any_agent"),
        )
        report = validate_workflow(wf)  # no registry
        assert report.is_valid


class TestEmptyContainers:
    def test_empty_sequence(self):
        wf = WorkflowDefinition(
            name="test",
            root=SequenceNode(steps=[]),
        )
        report = validate_workflow(wf)
        assert not report.is_valid
        assert any(e.code == "EMPTY_SEQUENCE" for e in report.errors)

    def test_empty_parallel(self):
        wf = WorkflowDefinition(
            name="test",
            root=ParallelNode(branches=[]),
        )
        report = validate_workflow(wf)
        assert not report.is_valid
        assert any(e.code == "EMPTY_PARALLEL" for e in report.errors)

    def test_nested_empty_sequence(self):
        wf = WorkflowDefinition(
            name="test",
            root=SequenceNode(steps=[
                AgentNode(agent="a"),
                SequenceNode(steps=[]),  # empty nested
            ]),
        )
        report = validate_workflow(wf)
        assert not report.is_valid
        assert any("steps[1]" in e.path for e in report.errors)

    def test_non_empty_containers_pass(self):
        wf = WorkflowDefinition(
            name="test",
            root=SequenceNode(steps=[AgentNode(agent="a")]),
        )
        report = validate_workflow(wf)
        assert report.is_valid


class TestConditionExpression:
    def test_empty_expression(self):
        wf = WorkflowDefinition(
            name="test",
            root=ConditionNode(
                expression="   ",
                true_branch=AgentNode(agent="a"),
                false_branch=AgentNode(agent="b"),
            ),
        )
        report = validate_workflow(wf)
        assert not report.is_valid
        assert any(e.code == "EMPTY_EXPRESSION" for e in report.errors)

    def test_valid_expression(self):
        wf = WorkflowDefinition(
            name="test",
            root=ConditionNode(
                expression="x > 0",
                true_branch=AgentNode(agent="a"),
                false_branch=AgentNode(agent="b"),
            ),
        )
        report = validate_workflow(wf)
        assert report.is_valid


class TestMaxDepth:
    def test_under_max_depth(self):
        wf = WorkflowDefinition(
            name="test",
            root=SequenceNode(steps=[AgentNode(agent="a")]),
        )
        report = validate_workflow(wf, max_depth=5)
        assert report.is_valid

    def test_exceeds_max_depth(self):
        # Build a deeply nested structure
        inner = AgentNode(agent="a")
        for _ in range(25):
            inner = SequenceNode(steps=[inner])

        wf = WorkflowDefinition(name="test", root=inner)
        report = validate_workflow(wf, max_depth=20)
        assert not report.is_valid
        assert any(e.code == "MAX_DEPTH_EXCEEDED" for e in report.errors)


class TestValidateWorkflowDict:
    def test_valid_dict(self):
        data = {
            "name": "test",
            "root": {"type": "agent", "agent": "researcher"},
        }
        report = validate_workflow_dict(data)
        assert report.is_valid

    def test_invalid_schema(self):
        data = {
            "name": "",
            "root": {"type": "unknown", "agent": "x"},
        }
        report = validate_workflow_dict(data)
        assert not report.is_valid
        # Should have schema-level errors
        assert any(e.code == "SCHEMA_ERROR" for e in report.errors)

    def test_dict_with_agent_registry(self):
        data = {
            "name": "test",
            "root": {"type": "agent", "agent": "missing_agent"},
        }
        registry = AgentRegistry.from_list(["researcher"])
        report = validate_workflow_dict(data, agent_registry=registry)
        assert not report.is_valid
        assert any(e.code == "AGENT_NOT_FOUND" for e in report.errors)


class TestValidateWorkflowJson:
    def test_valid_json(self):
        json_str = '{"name": "test", "root": {"type": "agent", "agent": "a"}}'
        report = validate_workflow_json(json_str)
        assert report.is_valid

    def test_invalid_json_syntax(self):
        json_str = 'not valid json'
        report = validate_workflow_json(json_str)
        assert not report.is_valid

    def test_valid_json_with_errors(self):
        json_str = '{"name": "", "root": {"type": "agent", "agent": "a"}}'
        report = validate_workflow_json(json_str)
        assert not report.is_valid


class TestComplexWorkflowValidation:
    def test_research_pipeline_valid(self):
        wf = WorkflowDefinition(
            name="research_pipeline",
            root=SequenceNode(steps=[
                AgentNode(agent="researcher"),
                ConditionNode(
                    expression="needs_review",
                    true_branch=LoopNode(
                        max_iterations=3,
                        body=AgentNode(agent="reviewer"),
                    ),
                    false_branch=AgentNode(agent="writer"),
                ),
                AgentNode(agent="publisher"),
            ]),
        )
        registry = AgentRegistry.from_list(
            ["researcher", "reviewer", "writer", "publisher"]
        )
        report = validate_workflow(wf, agent_registry=registry)
        assert report.is_valid

    def test_research_pipeline_missing_agent(self):
        wf = WorkflowDefinition(
            name="research_pipeline",
            root=SequenceNode(steps=[
                AgentNode(agent="researcher"),
                AgentNode(agent="writer"),
            ]),
        )
        registry = AgentRegistry.from_list(["researcher"])  # writer missing
        report = validate_workflow(wf, agent_registry=registry)
        assert not report.is_valid
        assert any("writer" in e.message for e in report.errors)
