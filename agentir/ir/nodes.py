"""AgentIR Workflow Nodes.

Defines the core node types that compose an agent workflow.
All nodes are framework-agnostic and form the intermediate representation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AgentNode(BaseModel):
    """A single agent invocation node.

    Each agent node can optionally specify an ``instruction`` that serves
    as the system prompt for this specific invocation. If not provided,
    the compiler uses the agent's default instruction from the registry.

    Example:
        {
            "type": "agent",
            "agent": "researcher",
            "instruction": "Research the latest AI trends and summarize key findings"
        }
    """

    type: Literal["agent"] = "agent"
    agent: str = Field(..., description="Identifier of the agent to invoke")
    instruction: str = Field(
        "",
        description="Optional system prompt / instruction for this specific agent invocation",
    )


class SequenceNode(BaseModel):
    """Executes steps sequentially in order.

    Example:
        {
            "type": "sequence",
            "steps": [
                {"type": "agent", "agent": "researcher"},
                {"type": "agent", "agent": "writer"}
            ]
        }
    """

    type: Literal["sequence"] = "sequence"
    steps: list[WorkflowNode] = Field(
        default_factory=list, description="Ordered list of workflow nodes"
    )


class ParallelNode(BaseModel):
    """Executes branches concurrently.

    Example:
        {
            "type": "parallel",
            "branches": [
                {"type": "agent", "agent": "translator_en"},
                {"type": "agent", "agent": "translator_zh"}
            ]
        }
    """

    type: Literal["parallel"] = "parallel"
    branches: list[WorkflowNode] = Field(
        default_factory=list, description="Workflow nodes to execute in parallel"
    )


class ConditionNode(BaseModel):
    """Branching based on a condition expression.

    Example:
        {
            "type": "condition",
            "expression": "output.quality_score > 0.8",
            "true_branch": {"type": "agent", "agent": "publisher"},
            "false_branch": {"type": "agent", "agent": "reviser"}
        }
    """

    type: Literal["condition"] = "condition"
    expression: str = Field(
        ..., description="Condition expression evaluated at runtime"
    )
    true_branch: WorkflowNode = Field(
        ..., description="Workflow node executed when condition is true"
    )
    false_branch: WorkflowNode = Field(
        ..., description="Workflow node executed when condition is false"
    )


class LoopNode(BaseModel):
    """Repeatedly executes a body node up to a maximum number of iterations.

    Example:
        {
            "type": "loop",
            "max_iterations": 3,
            "body": {"type": "agent", "agent": "reviewer"}
        }
    """

    type: Literal["loop"] = "loop"
    max_iterations: int = Field(..., gt=0, description="Maximum loop iterations")
    body: WorkflowNode = Field(..., description="Workflow node to execute in the loop")


class ToolNode(BaseModel):
    """Invokes a user-defined Python tool as a workflow node.

    Tools are Python scripts in the ``tools/`` directory. Each tool is
    a standard async function (by convention named ``execute``) that
    the system discovers and wraps as an ADK @node function.

    Example:
        {
            "type": "tool",
            "tool": "web_search"
        }
    """

    type: Literal["tool"] = "tool"
    tool: str = Field(..., description="Name of the tool to invoke (matches registry)")


class SubWorkflowNode(BaseModel):
    """References another workflow as a reusable sub-workflow.

    The referenced workflow is loaded by name from the artifact store
    and executed inline within the parent workflow.

    Example:
        {
            "type": "subworkflow",
            "workflow": "data_pipeline",
            "params": {}
        }
    """

    type: Literal["subworkflow"] = "subworkflow"
    workflow: str = Field(
        ..., description="Name of the sub-workflow to invoke"
    )
    params: dict[str, str] = Field(
        default_factory=dict,
        description="Optional parameters to pass to the sub-workflow",
    )


# ---- Discriminated Union ----

WorkflowNode = Annotated[
    AgentNode
    | SequenceNode
    | ParallelNode
    | ConditionNode
    | LoopNode
    | ToolNode
    | SubWorkflowNode,
    Field(discriminator="type"),
]


# Resolve forward references for recursive models
SequenceNode.model_rebuild()
ParallelNode.model_rebuild()
ConditionNode.model_rebuild()
LoopNode.model_rebuild()
