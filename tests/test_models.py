"""Tests for top-level WorkflowDefinition model."""

import pytest
from pydantic import ValidationError

from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import AgentNode, ConditionNode, LoopNode, ParallelNode, SequenceNode


class TestWorkflowDefinition:
    def test_minimal_workflow(self):
        wf = WorkflowDefinition(
            name="test_workflow",
            root=AgentNode(agent="researcher"),
        )
        assert wf.name == "test_workflow"
        assert wf.version == "0.1.0"
        assert wf.description == ""
        assert wf.root.agent == "researcher"

    def test_workflow_with_all_fields(self):
        wf = WorkflowDefinition(
            name="research_pipeline",
            version="1.0.0",
            description="A complete research pipeline",
            root=SequenceNode(
                steps=[
                    AgentNode(agent="researcher"),
                    AgentNode(agent="writer"),
                ]
            ),
        )
        assert wf.name == "research_pipeline"
        assert wf.version == "1.0.0"
        assert wf.description == "A complete research pipeline"
        assert len(wf.root.steps) == 2

    def test_workflow_from_dict(self):
        data = {
            "name": "test",
            "version": "0.1.0",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "researcher"},
                    {"type": "agent", "agent": "writer"},
                ],
            },
        }
        wf = WorkflowDefinition.model_validate(data)
        assert wf.name == "test"
        assert isinstance(wf.root, SequenceNode)
        assert len(wf.root.steps) == 2

    def test_workflow_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            WorkflowDefinition(
                name="",
                root=AgentNode(agent="test"),
            )

    def test_workflow_rejects_missing_root(self):
        with pytest.raises(ValidationError):
            WorkflowDefinition.model_validate({"name": "test"})

    def test_workflow_serialization_roundtrip(self):
        wf = WorkflowDefinition(
            name="test",
            version="0.2.0",
            description="desc",
            root=ConditionNode(
                expression="x",
                true_branch=AgentNode(agent="a"),
                false_branch=LoopNode(
                    max_iterations=2,
                    body=AgentNode(agent="b"),
                ),
            ),
        )
        data = wf.model_dump()
        restored = WorkflowDefinition.model_validate(data)
        assert restored.name == "test"
        assert restored.version == "0.2.0"
        assert isinstance(restored.root, ConditionNode)
        assert isinstance(restored.root.false_branch, LoopNode)

    def test_workflow_json_serialization(self):
        wf = WorkflowDefinition(
            name="test",
            root=AgentNode(agent="researcher"),
        )
        json_str = wf.model_dump_json(indent=2)
        assert "test" in json_str
        assert "agent" in json_str
        restored = WorkflowDefinition.model_validate_json(json_str)
        assert restored.name == "test"


class TestComplexWorkflows:
    """Test real-world complex workflow structures."""

    def test_research_write_pipeline(self):
        """A typical research → review → write pipeline."""
        wf = WorkflowDefinition(
            name="research_pipeline",
            description="Research, review, and write workflow",
            root=SequenceNode(
                steps=[
                    AgentNode(agent="researcher"),
                    ConditionNode(
                        expression="output.needs_review",
                        true_branch=LoopNode(
                            max_iterations=3,
                            body=AgentNode(agent="reviewer"),
                        ),
                        false_branch=AgentNode(agent="writer"),
                    ),
                    AgentNode(agent="publisher"),
                ]
            ),
        )
        data = wf.model_dump()
        restored = WorkflowDefinition.model_validate(data)
        assert isinstance(restored.root, SequenceNode)
        assert len(restored.root.steps) == 3

    def test_parallel_translation_pipeline(self):
        """A parallel translation workflow."""
        wf = WorkflowDefinition(
            name="translation_pipeline",
            root=SequenceNode(
                steps=[
                    AgentNode(agent="extractor"),
                    ParallelNode(
                        branches=[
                            AgentNode(agent="translator_en"),
                            AgentNode(agent="translator_zh"),
                            AgentNode(agent="translator_ja"),
                        ]
                    ),
                    AgentNode(agent="merger"),
                ]
            ),
        )
        data = wf.model_dump()
        restored = WorkflowDefinition.model_validate(data)
        seq = restored.root
        assert isinstance(seq, SequenceNode)
        parallel = seq.steps[1]
        assert isinstance(parallel, ParallelNode)
        assert len(parallel.branches) == 3

    def test_deeply_nested_workflow(self):
        """A deeply nested workflow to stress-test recursion."""
        wf = WorkflowDefinition(
            name="deep_nested",
            root=SequenceNode(
                steps=[
                    ConditionNode(
                        expression="a",
                        true_branch=LoopNode(
                            max_iterations=5,
                            body=SequenceNode(
                                steps=[
                                    AgentNode(agent="a1"),
                                    ConditionNode(
                                        expression="b",
                                        true_branch=AgentNode(agent="b1"),
                                        false_branch=ParallelNode(
                                            branches=[
                                                AgentNode(agent="c1"),
                                                AgentNode(agent="c2"),
                                            ]
                                        ),
                                    ),
                                ]
                            ),
                        ),
                        false_branch=AgentNode(agent="fallback"),
                    )
                ]
            ),
        )
        data = wf.model_dump()
        restored = WorkflowDefinition.model_validate(data)
        assert restored.name == "deep_nested"
        # Verify deep structure survives roundtrip
        root_seq = restored.root
        assert isinstance(root_seq, SequenceNode)
        cond = root_seq.steps[0]
        assert isinstance(cond, ConditionNode)
        loop = cond.true_branch
        assert isinstance(loop, LoopNode)
        assert loop.max_iterations == 5
