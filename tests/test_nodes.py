"""Tests for AgentIR node types."""

import pytest
from pydantic import ValidationError

from agentir.ir.nodes import (
    AgentNode,
    ConditionNode,
    LoopNode,
    ParallelNode,
    SequenceNode,
)


class TestAgentNode:
    def test_minimal_agent_node(self):
        node = AgentNode(agent="researcher")
        assert node.type == "agent"
        assert node.agent == "researcher"

    def test_agent_node_serialization(self):
        node = AgentNode(agent="researcher")
        data = node.model_dump()
        assert data == {"type": "agent", "agent": "researcher"}

    def test_agent_node_deserialization(self):
        node = AgentNode.model_validate({"type": "agent", "agent": "researcher"})
        assert node.agent == "researcher"

    def test_agent_node_requires_agent_field(self):
        with pytest.raises(ValidationError):
            AgentNode.model_validate({"type": "agent"})


class TestSequenceNode:
    def test_empty_sequence(self):
        node = SequenceNode(steps=[])
        assert node.type == "sequence"
        assert node.steps == []

    def test_sequence_with_agent_steps(self):
        node = SequenceNode(
            steps=[
                AgentNode(agent="researcher"),
                AgentNode(agent="writer"),
            ]
        )
        assert len(node.steps) == 2
        assert node.steps[0].agent == "researcher"
        assert node.steps[1].agent == "writer"

    def test_sequence_nested(self):
        node = SequenceNode(
            steps=[
                AgentNode(agent="researcher"),
                SequenceNode(
                    steps=[
                        AgentNode(agent="reviewer"),
                        AgentNode(agent="publisher"),
                    ]
                ),
            ]
        )
        assert len(node.steps) == 2
        assert isinstance(node.steps[1], SequenceNode)
        assert len(node.steps[1].steps) == 2  # type: ignore[union-attr]

    def test_sequence_serialization_roundtrip(self):
        node = SequenceNode(
            steps=[
                AgentNode(agent="researcher"),
                AgentNode(agent="writer"),
            ]
        )
        data = node.model_dump()
        restored = SequenceNode.model_validate(data)
        assert len(restored.steps) == 2
        assert restored.steps[0].agent == "researcher"

    def test_sequence_from_dict(self):
        data = {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "agent", "agent": "writer"},
            ],
        }
        node = SequenceNode.model_validate(data)
        assert len(node.steps) == 2
        assert node.steps[0].agent == "researcher"
        assert node.steps[1].agent == "writer"


class TestParallelNode:
    def test_empty_parallel(self):
        node = ParallelNode(branches=[])
        assert node.type == "parallel"
        assert node.branches == []

    def test_parallel_with_agents(self):
        node = ParallelNode(
            branches=[
                AgentNode(agent="translator_en"),
                AgentNode(agent="translator_zh"),
            ]
        )
        assert len(node.branches) == 2

    def test_parallel_serialization(self):
        node = ParallelNode(
            branches=[
                AgentNode(agent="t1"),
                AgentNode(agent="t2"),
            ]
        )
        data = node.model_dump()
        assert data["type"] == "parallel"
        assert len(data["branches"]) == 2

    def test_parallel_deserialization(self):
        data = {
            "type": "parallel",
            "branches": [
                {"type": "agent", "agent": "t1"},
                {"type": "agent", "agent": "t2"},
            ],
        }
        node = ParallelNode.model_validate(data)
        assert len(node.branches) == 2
        assert node.branches[0].agent == "t1"
        assert node.branches[1].agent == "t2"


class TestConditionNode:
    def test_basic_condition(self):
        node = ConditionNode(
            expression="need_retry",
            true_branch=AgentNode(agent="retry_handler"),
            false_branch=AgentNode(agent="success_handler"),
        )
        assert node.type == "condition"
        assert node.expression == "need_retry"
        assert node.true_branch.agent == "retry_handler"
        assert node.false_branch.agent == "success_handler"

    def test_condition_serialization(self):
        node = ConditionNode(
            expression="score > 0.8",
            true_branch=AgentNode(agent="publisher"),
            false_branch=AgentNode(agent="reviser"),
        )
        data = node.model_dump()
        assert data["type"] == "condition"
        assert data["expression"] == "score > 0.8"

    def test_condition_deserialization(self):
        data = {
            "type": "condition",
            "expression": "score > 0.8",
            "true_branch": {"type": "agent", "agent": "publisher"},
            "false_branch": {"type": "agent", "agent": "reviser"},
        }
        node = ConditionNode.model_validate(data)
        assert node.expression == "score > 0.8"

    def test_condition_requires_expression(self):
        with pytest.raises(ValidationError):
            ConditionNode.model_validate({
                "type": "condition",
                "true_branch": {"type": "agent", "agent": "a"},
                "false_branch": {"type": "agent", "agent": "b"},
            })

    def test_nested_condition(self):
        node = ConditionNode(
            expression="step1",
            true_branch=ConditionNode(
                expression="step2",
                true_branch=AgentNode(agent="a"),
                false_branch=AgentNode(agent="b"),
            ),
            false_branch=AgentNode(agent="c"),
        )
        assert isinstance(node.true_branch, ConditionNode)
        assert node.true_branch.expression == "step2"


class TestLoopNode:
    def test_basic_loop(self):
        node = LoopNode(
            max_iterations=3,
            body=AgentNode(agent="reviewer"),
        )
        assert node.type == "loop"
        assert node.max_iterations == 3
        assert node.body.agent == "reviewer"

    def test_loop_serialization(self):
        node = LoopNode(
            max_iterations=5,
            body=AgentNode(agent="retry_agent"),
        )
        data = node.model_dump()
        assert data["type"] == "loop"
        assert data["max_iterations"] == 5

    def test_loop_deserialization(self):
        data = {
            "type": "loop",
            "max_iterations": 3,
            "body": {"type": "agent", "agent": "reviewer"},
        }
        node = LoopNode.model_validate(data)
        assert node.max_iterations == 3

    def test_loop_rejects_zero_iterations(self):
        with pytest.raises(ValidationError):
            LoopNode(
                max_iterations=0,
                body=AgentNode(agent="reviewer"),
            )

    def test_loop_rejects_negative_iterations(self):
        with pytest.raises(ValidationError):
            LoopNode(
                max_iterations=-1,
                body=AgentNode(agent="reviewer"),
            )

    def test_nested_loop(self):
        node = LoopNode(
            max_iterations=2,
            body=SequenceNode(
                steps=[
                    AgentNode(agent="reviewer"),
                    LoopNode(
                        max_iterations=3,
                        body=AgentNode(agent="sub_checker"),
                    ),
                ]
            ),
        )
        assert node.max_iterations == 2
        inner_seq = node.body
        assert isinstance(inner_seq, SequenceNode)
        inner_loop = inner_seq.steps[1]
        assert isinstance(inner_loop, LoopNode)
        assert inner_loop.max_iterations == 3


class TestDiscriminatedUnion:
    """Test that the discriminated union correctly resolves node types."""

    def test_union_deserializes_agent(self):
        from agentir.ir.nodes import WorkflowNode

        data = {"type": "agent", "agent": "test"}
        node = AgentNode.model_validate(data)
        assert isinstance(node, AgentNode)

    def test_union_deserializes_sequence(self):
        data = {
            "type": "sequence",
            "steps": [{"type": "agent", "agent": "test"}],
        }
        node = SequenceNode.model_validate(data)
        assert isinstance(node, SequenceNode)

    def test_union_deserializes_parallel(self):
        data = {
            "type": "parallel",
            "branches": [{"type": "agent", "agent": "test"}],
        }
        node = ParallelNode.model_validate(data)
        assert isinstance(node, ParallelNode)

    def test_union_deserializes_condition(self):
        data = {
            "type": "condition",
            "expression": "x > 0",
            "true_branch": {"type": "agent", "agent": "a"},
            "false_branch": {"type": "agent", "agent": "b"},
        }
        node = ConditionNode.model_validate(data)
        assert isinstance(node, ConditionNode)

    def test_union_deserializes_loop(self):
        data = {
            "type": "loop",
            "max_iterations": 3,
            "body": {"type": "agent", "agent": "test"},
        }
        node = LoopNode.model_validate(data)
        assert isinstance(node, LoopNode)

    def test_union_rejects_unknown_type(self):
        with pytest.raises(ValidationError):
            AgentNode.model_validate({"type": "unknown", "agent": "test"})
