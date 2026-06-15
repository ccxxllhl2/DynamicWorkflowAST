"""Schema-level utilities: serialization, deserialization, and JSON Schema generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import WorkflowNode


def workflow_to_dict(workflow: WorkflowDefinition) -> dict[str, Any]:
    """Serialize a WorkflowDefinition to a plain dictionary."""
    return workflow.model_dump(mode="python")


def workflow_to_json(workflow: WorkflowDefinition, indent: int = 2) -> str:
    """Serialize a WorkflowDefinition to a JSON string."""
    return workflow.model_dump_json(indent=indent)


def workflow_from_dict(data: dict[str, Any]) -> WorkflowDefinition:
    """Deserialize a dictionary into a WorkflowDefinition."""
    return WorkflowDefinition.model_validate(data)


def workflow_from_json(json_str: str) -> WorkflowDefinition:
    """Deserialize a JSON string into a WorkflowDefinition."""
    return WorkflowDefinition.model_validate_json(json_str)


def workflow_from_file(path: str | Path) -> WorkflowDefinition:
    """Load a WorkflowDefinition from a JSON file."""
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        return workflow_from_json(f.read())


def workflow_to_file(workflow: WorkflowDefinition, path: str | Path) -> None:
    """Save a WorkflowDefinition to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(workflow_to_json(workflow))


def node_to_dict(node: WorkflowNode) -> dict[str, Any]:
    """Serialize a single WorkflowNode to a plain dictionary."""
    return node.model_dump(mode="python")


def node_to_json(node: WorkflowNode, indent: int = 2) -> str:
    """Serialize a single WorkflowNode to a JSON string."""
    return node.model_dump_json(indent=indent)


def generate_json_schema() -> dict[str, Any]:
    """Generate the JSON Schema for WorkflowDefinition."""
    return WorkflowDefinition.model_json_schema()
