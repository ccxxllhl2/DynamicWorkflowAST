"""Validation rules for AgentIR workflows.

Each rule is a deterministic, stateless function that checks one aspect
of a workflow and returns a list of ValidationError objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import (
    AgentNode,
    ConditionNode,
    LoopNode,
    ParallelNode,
    SequenceNode,
    ToolNode,
    WorkflowNode,
)
from agentir.tools.registry import ToolRegistry


@dataclass
class ValidationError:
    """A single validation error."""

    code: str
    message: str
    path: str = ""  # dot-separated path to the problematic node, e.g. "root.steps[0]"

    def __str__(self) -> str:
        loc = f" at '{self.path}'" if self.path else ""
        return f"[{self.code}]{loc}: {self.message}"


@dataclass
class AgentRegistry:
    """Registry of available agent names that can be referenced in workflows."""

    agents: set[str] = field(default_factory=set)

    @classmethod
    def from_list(cls, names: list[str]) -> AgentRegistry:
        return cls(agents=set(names))

    def has(self, name: str) -> bool:
        return name in self.agents


# ---- Built-in Rules ----

def _walk_nodes(
    node: WorkflowNode,
    visitor: Callable[[WorkflowNode, str], list[ValidationError]],
    path: str = "root",
) -> list[ValidationError]:
    """Walk the workflow tree depth-first, calling visitor for each node."""
    errors: list[ValidationError] = []
    errors.extend(visitor(node, path))

    if isinstance(node, SequenceNode):
        for i, step in enumerate(node.steps):
            errors.extend(_walk_nodes(step, visitor, f"{path}.steps[{i}]"))
    elif isinstance(node, ParallelNode):
        for i, branch in enumerate(node.branches):
            errors.extend(_walk_nodes(branch, visitor, f"{path}.branches[{i}]"))
    elif isinstance(node, ConditionNode):
        errors.extend(_walk_nodes(node.true_branch, visitor, f"{path}.true_branch"))
        errors.extend(_walk_nodes(node.false_branch, visitor, f"{path}.false_branch"))
    elif isinstance(node, LoopNode):
        errors.extend(_walk_nodes(node.body, visitor, f"{path}.body"))
    elif isinstance(node, ToolNode):
        pass  # Leaf node, no children

    return errors


def validate_agent_existence(
    workflow: WorkflowDefinition, registry: AgentRegistry
) -> list[ValidationError]:
    """Validate that all referenced agents exist in the registry."""

    def check(node: WorkflowNode, path: str) -> list[ValidationError]:
        if isinstance(node, AgentNode) and not registry.has(node.agent):
            return [
                ValidationError(
                    code="AGENT_NOT_FOUND",
                    message=f"Agent '{node.agent}' is not registered",
                    path=path,
                )
            ]
        return []

    return _walk_nodes(workflow.root, check)


def validate_no_empty_containers(
    workflow: WorkflowDefinition,
) -> list[ValidationError]:
    """Validate that Sequence and Parallel nodes are not empty."""

    def check(node: WorkflowNode, path: str) -> list[ValidationError]:
        if isinstance(node, SequenceNode) and len(node.steps) == 0:
            return [
                ValidationError(
                    code="EMPTY_SEQUENCE",
                    message="Sequence node has no steps",
                    path=path,
                )
            ]
        if isinstance(node, ParallelNode) and len(node.branches) == 0:
            return [
                ValidationError(
                    code="EMPTY_PARALLEL",
                    message="Parallel node has no branches",
                    path=path,
                )
            ]
        return []

    return _walk_nodes(workflow.root, check)


def validate_condition_expression(
    workflow: WorkflowDefinition,
) -> list[ValidationError]:
    """Validate that condition expressions are non-empty."""
    errors: list[ValidationError] = []

    def check(node: WorkflowNode, path: str) -> list[ValidationError]:
        if isinstance(node, ConditionNode) and not node.expression.strip():
            return [
                ValidationError(
                    code="EMPTY_EXPRESSION",
                    message="Condition expression must not be empty",
                    path=path,
                )
            ]
        return []

    return _walk_nodes(workflow.root, check)


def validate_tool_existence(
    workflow: WorkflowDefinition, registry: ToolRegistry
) -> list[ValidationError]:
    """Validate that all referenced tools exist in the registry."""

    def check(node: WorkflowNode, path: str) -> list[ValidationError]:
        if isinstance(node, ToolNode) and not registry.has(node.tool):
            return [
                ValidationError(
                    code="TOOL_NOT_FOUND",
                    message=f"Tool '{node.tool}' is not registered",
                    path=path,
                )
            ]
        return []

    return _walk_nodes(workflow.root, check)


def validate_max_depth(
    workflow: WorkflowDefinition, max_depth: int = 20
) -> list[ValidationError]:
    """Validate that workflow nesting does not exceed max_depth."""

    def measure_depth(node: WorkflowNode) -> int:
        if isinstance(node, (AgentNode, ToolNode)):
            return 1
        if isinstance(node, SequenceNode):
            return 1 + max((measure_depth(s) for s in node.steps), default=0)
        if isinstance(node, ParallelNode):
            return 1 + max((measure_depth(b) for b in node.branches), default=0)
        if isinstance(node, ConditionNode):
            return 1 + max(measure_depth(node.true_branch), measure_depth(node.false_branch))
        if isinstance(node, LoopNode):
            return 1 + measure_depth(node.body)
        return 1

    depth = measure_depth(workflow.root)
    if depth > max_depth:
        return [
            ValidationError(
                code="MAX_DEPTH_EXCEEDED",
                message=f"Workflow depth {depth} exceeds maximum {max_depth}",
            )
        ]
    return []
