"""AgentIR Validator.

Deterministic validation of WorkflowDefinitions. No LLM involvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError as PydanticValidationError

from agentir.ir.models import WorkflowDefinition
from agentir.ir.schema import workflow_from_dict, workflow_from_json
from agentir.validator.rules import (
    AgentRegistry,
    ValidationError,
    validate_agent_existence,
    validate_condition_expression,
    validate_max_depth,
    validate_no_empty_containers,
    validate_tool_existence,
)
from agentir.tools.registry import ToolRegistry


@dataclass
class ValidationReport:
    """Result of validating a workflow.

    Attributes:
        is_valid: True if no errors were found.
        errors: List of validation errors (empty if valid).
        warnings: List of non-fatal warnings (always empty in current version).
    """

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def summary(self) -> str:
        if self.is_valid:
            return "✓ Workflow is valid"
        lines = [f"✗ {len(self.errors)} validation error(s):"]
        for err in self.errors:
            lines.append(f"  {err}")
        return "\n".join(lines)


def validate_workflow(
    workflow: WorkflowDefinition,
    agent_registry: AgentRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    max_depth: int = 20,
) -> ValidationReport:
    """Run all validation rules on a workflow.

    Args:
        workflow: The workflow to validate.
        agent_registry: Optional registry of available agents.
        tool_registry: Optional registry of available tools.
        max_depth: Maximum allowed nesting depth.

    Returns:
        A ValidationReport with the results.
    """
    errors: list[ValidationError] = []

    # Structural rules (always applied)
    errors.extend(validate_no_empty_containers(workflow))
    errors.extend(validate_condition_expression(workflow))
    errors.extend(validate_max_depth(workflow, max_depth))

    # Agent existence (only if registry is provided)
    if agent_registry is not None:
        errors.extend(validate_agent_existence(workflow, agent_registry))

    # Tool existence (only if registry is provided)
    if tool_registry is not None:
        errors.extend(validate_tool_existence(workflow, tool_registry))

    return ValidationReport(
        is_valid=len(errors) == 0,
        errors=errors,
    )


def validate_workflow_dict(
    data: dict,
    agent_registry: AgentRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    max_depth: int = 20,
) -> ValidationReport:
    """Validate a workflow from a raw dictionary.

    This first validates the schema via Pydantic, then runs semantic rules.
    """
    try:
        workflow = workflow_from_dict(data)
    except PydanticValidationError as e:
        pydantic_errors: list[ValidationError] = []
        for err in e.errors():
            loc = ".".join(str(l) for l in err["loc"])
            pydantic_errors.append(
                ValidationError(
                    code="SCHEMA_ERROR",
                    message=err["msg"],
                    path=loc,
                )
            )
        return ValidationReport(is_valid=False, errors=pydantic_errors)

    return validate_workflow(workflow, agent_registry, tool_registry, max_depth)


def validate_workflow_json(
    json_str: str,
    agent_registry: AgentRegistry | None = None,
    tool_registry: ToolRegistry | None = None,
    max_depth: int = 20,
) -> ValidationReport:
    """Validate a workflow from a JSON string."""
    try:
        workflow = workflow_from_json(json_str)
    except PydanticValidationError as e:
        pydantic_errors: list[ValidationError] = []
        for err in e.errors():
            loc = ".".join(str(l) for l in err["loc"])
            pydantic_errors.append(
                ValidationError(
                    code="SCHEMA_ERROR",
                    message=err["msg"],
                    path=loc,
                )
            )
        return ValidationReport(is_valid=False, errors=pydantic_errors)

    return validate_workflow(workflow, agent_registry, tool_registry, max_depth)
