"""Top-level workflow model definitions."""

from pydantic import BaseModel, Field

from agentir.ir.nodes import WorkflowNode


class WorkflowDefinition(BaseModel):
    """Root definition of an AgentIR workflow.

    Contains metadata and the root workflow node.

    Example:
        {
            "name": "research_pipeline",
            "version": "0.1.0",
            "description": "A simple research -> write pipeline",
            "root": {
                "type": "sequence",
                "steps": [
                    {"type": "agent", "agent": "researcher"},
                    {"type": "agent", "agent": "writer"}
                ]
            }
        }
    """

    name: str = Field(..., min_length=1, description="Unique workflow name")
    version: str = Field(default="0.1.0", description="Workflow version")
    description: str = Field(default="", description="Human-readable description")
    root: WorkflowNode = Field(..., description="Root node of the workflow graph")
