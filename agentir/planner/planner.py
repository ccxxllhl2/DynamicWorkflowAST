"""AgentIR Planner — Natural Language → AgentIR Workflow.

Converts natural language descriptions of agent workflows into valid
AgentIR WorkflowDefinitions using an LLM-driven planning loop with
built-in validation and automatic retry on errors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from agentir.ir.models import WorkflowDefinition
from agentir.ir.schema import workflow_from_dict
from agentir.ir.nodes import (
    AgentNode,
    ConditionNode,
    LoopNode,
    ParallelNode,
    SequenceNode,
    ToolNode,
)
from agentir.validator.validator import validate_workflow_dict, ValidationReport
from agentir.llm.config import LLMConfig
from agentir.llm.client import create_llm_callable
from agentir.tools.registry import ToolRegistry


# ---- Prompt Template ----

_SYSTEM_PROMPT = """\
You are a workflow planner for AgentIR, a framework-agnostic agent workflow system.
Your task is to convert a natural language description of an agent workflow into
a valid AgentIR JSON document.

## AgentIR Schema

The workflow has this structure:
```json
{
  "name": "<snake_case_name>",
  "version": "0.1.0",
  "description": "<short human-readable description>",
  "root": { ... }
}
```

The "root" is a workflow node tree built from 6 node types:

### 1. AgentNode — Invoke a single agent
```json
{ "type": "agent", "agent": "<agent_name>" }
```

### 2. SequenceNode — Run steps one after another (in order)
```json
{
  "type": "sequence",
  "steps": [ <node>, <node>, ... ]
}
```
Use this when tasks must happen sequentially. Each step is a workflow node.

### 3. ParallelNode — Run branches concurrently
```json
{
  "type": "parallel",
  "branches": [ <node>, <node>, ... ]
}
```
Use this for independent tasks that can run at the same time.

### 4. ConditionNode — Branch based on a runtime expression
```json
{
  "type": "condition",
  "expression": "<python-like expression, e.g. 'output.quality > 0.8'>",
  "true_branch": <node>,
  "false_branch": <node>
}
```
The expression is evaluated at runtime. Use descriptive field names like
"output.confidence", "output.is_valid", "output.needs_review", etc.

### 5. LoopNode — Repeat a body up to max_iterations
```json
{
  "type": "loop",
  "max_iterations": <positive integer>,
  "body": <node>
}
```
Use this for review-retry loops, quality check loops, iterative refinement, etc.
max_iterations must be a positive integer.

### 6. ToolNode — Invoke a user-defined Python tool
```json
{ "type": "tool", "tool": "<tool_name>" }
```
Use this when the user mentions a specific capability like "search", "calculate",
"fetch", "send email", etc. that matches an available tool.
{tool_context}

## Key Rules
- Nodes can be nested arbitrarily (any node can contain any other node)
- Always use a "sequence" as the top-level root node for multi-step workflows
- agent names should be lowercase_snake_case
- tool names must exactly match the available tools listed above
- Every "sequence" must have at least 1 step
- Every "parallel" must have at least 2 branches (or 1 if the user insists)
- "condition" must have a non-empty expression and both branches
- "loop" must have max_iterations > 0 and a body

## Output Format
Return ONLY a valid JSON object. No markdown code fences, no explanation, no extra text.
The response must be a single JSON object that can be parsed by json.loads().
"""

_USER_PROMPT_TEMPLATE = """\
Convert the following natural language description into an AgentIR workflow JSON:

{description}"""

_ERROR_PROMPT_TEMPLATE = """\
Your previous output had validation errors. Here are the errors:
{errors}

Please fix these errors and return ONLY the corrected JSON object.
Do not include any markdown formatting or extra text."""


# ---- Constants ----

DEFAULT_MAX_RETRIES = 3

# ---- Plan Result ----

@dataclass
class PlanResult:
    """Result of planning a workflow from natural language.

    Attributes:
        workflow: The validated WorkflowDefinition (None if planning failed).
        success: Whether planning succeeded.
        raw_response: The raw LLM response that produced the final workflow.
        retries: Number of retries used.
        errors: Accumulated validation errors across all attempts.
    """

    workflow: WorkflowDefinition | None = None
    success: bool = False
    raw_response: str = ""
    retries: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any] | None:
        """Return the workflow as a dict, or None if planning failed."""
        if self.workflow is None:
            return None
        return self.workflow.model_dump(mode="python")

    def to_json(self, indent: int = 2) -> str | None:
        """Return the workflow as a JSON string, or None if planning failed."""
        if self.workflow is None:
            return None
        return self.workflow.model_dump_json(indent=indent)


# ---- Planner ----

@dataclass
class Planner:
    """Converts natural language descriptions into AgentIR WorkflowDefinitions.

    Uses an LLM for the planning step, then validates the result
    against the AgentIR schema. Automatically retries on validation failure
    with error feedback to the LLM.

    Two ways to provide LLM access:

    1. Via LLMConfig (recommended) — auto-creates the API client:
       config = LLMConfig.deepseek(api_key="sk-xxx")
       planner = Planner(llm_config=config)
       result = planner.plan("First research, then write, then publish")

    2. Via llm_callable (manual) — pass your own callable:
       def call_llm(prompt: str) -> str: ...
       planner = Planner(llm_callable=call_llm)

    Usage:
        # DeepSeek
        planner = Planner(llm_config=LLMConfig.deepseek(api_key="sk-xxx"))

        # OpenAI
        planner = Planner(llm_config=LLMConfig.openai())

        # Ollama (local)
        planner = Planner(llm_config=LLMConfig.ollama(model="llama3"))

        # Custom endpoint
        planner = Planner(llm_config=LLMConfig.custom(
            base_url="http://localhost:8000/v1", model="my-model"
        ))
    """

    llm_config: LLMConfig | None = None
    llm_callable: Callable[[str], str] | None = None
    max_retries: int = DEFAULT_MAX_RETRIES

    def __post_init__(self) -> None:
        """Resolve LLM callable from config if not provided directly."""
        if self.llm_callable is None:
            if self.llm_config is None:
                raise ValueError(
                    "Either llm_config or llm_callable must be provided to Planner. "
                    "Example: Planner(llm_config=LLMConfig.deepseek(api_key='sk-xxx'))"
                )
            self.llm_callable = create_llm_callable(self.llm_config)

    # ---- Public API ----

    def plan(
        self,
        description: str,
        available_tools: ToolRegistry | None = None,
    ) -> PlanResult:
        """Plan a workflow from a natural language description.

        Args:
            description: Natural language description of the desired workflow.
            available_tools: Optional registry of available user-defined tools.

        Returns:
            PlanResult containing the validated WorkflowDefinition or error details.
        """
        errors: list[str] = []
        prompt = self._build_prompt(description, available_tools)

        for attempt in range(self.max_retries + 1):
            # Call LLM
            try:
                raw_response = self.llm_callable(prompt)
            except Exception as e:
                errors.append(f"LLM call failed: {e}")
                continue

            if not raw_response or not raw_response.strip():
                errors.append("LLM returned empty response")
                continue

            # Parse JSON from response
            try:
                data = self._extract_json(raw_response)
            except ValueError as e:
                errors.append(f"JSON parse error: {e}")
                # If it's the last attempt, give up; otherwise, report error and retry
                if attempt >= self.max_retries:
                    return PlanResult(
                        success=False,
                        raw_response=raw_response,
                        retries=attempt,
                        errors=errors,
                    )
                prompt = self._build_error_prompt(raw_response, [str(e)])
                continue

            # Validate against AgentIR schema
            tool_registry = available_tools if available_tools else None
            report = validate_workflow_dict(data, tool_registry=tool_registry)
            if report.is_valid:
                # Success!
                workflow = workflow_from_dict(data)
                return PlanResult(
                    workflow=workflow,
                    success=True,
                    raw_response=raw_response,
                    retries=attempt,
                    errors=errors,
                )

            # Collect validation errors
            current_errors = [str(e) for e in report.errors]
            errors.extend(current_errors)

            if attempt >= self.max_retries:
                return PlanResult(
                    success=False,
                    raw_response=raw_response,
                    retries=attempt,
                    errors=errors,
                )

            # Build error feedback prompt for retry
            prompt = self._build_error_prompt(raw_response, current_errors)

        return PlanResult(
            success=False,
            retries=self.max_retries,
            errors=errors,
        )

    # ---- Planning with structured context ----

    def plan_with_context(
        self,
        description: str,
        available_agents: list[str] | None = None,
        available_tools: ToolRegistry | None = None,
        constraints: str | None = None,
    ) -> PlanResult:
        """Plan a workflow with additional context.

        Args:
            description: Natural language description of the desired workflow.
            available_agents: List of agent names available for the workflow.
            available_tools: Optional registry of available user-defined tools.
            constraints: Additional constraints or requirements in natural language.

        Returns:
            PlanResult containing the validated WorkflowDefinition or error details.
        """
        enhanced_description = description
        if available_agents:
            enhanced_description += "\n\nAvailable agents: " + ", ".join(available_agents)
        if constraints:
            enhanced_description += f"\n\nAdditional constraints: {constraints}"
        return self.plan(enhanced_description, available_tools=available_tools)

    # ---- Private Methods ----

    def _build_prompt(
        self, description: str, available_tools: ToolRegistry | None = None
    ) -> str:
        """Build the full LLM prompt from the NL description."""
        # Build tool context
        if available_tools is not None and available_tools.tools:
            tool_list = available_tools.to_prompt_context()
            tool_ctx = (
                "\n## Available Tools\n\n"
                "You may use the following tools as workflow nodes via\n"
                '`{"type": "tool", "tool": "<name>"}`:\n\n'
                f"{tool_list}"
            )
        else:
            tool_ctx = "\n(No custom tools are currently available. Only use agent nodes.)"

        # Use replace() instead of format() to avoid JSON brace conflicts
        prompt = _SYSTEM_PROMPT.replace("{tool_context}", tool_ctx)
        return prompt + "\n\n" + _USER_PROMPT_TEMPLATE.format(
            description=description
        )

    def _build_error_prompt(
        self, previous_response: str, errors: list[str]
    ) -> str:
        """Build a retry prompt with error feedback."""
        error_text = "\n".join(f"- {e}" for e in errors)
        # Use empty tool context for error prompts (tools don't matter on retry)
        sys_prompt = _SYSTEM_PROMPT.replace(
            "{tool_context}",
            "\n(No custom tools are currently available. Only use agent nodes.)",
        )
        return (
            sys_prompt
            + "\n\n"
            + _ERROR_PROMPT_TEMPLATE.format(errors=error_text)
            + "\n\nPrevious output was:\n\n"
            + previous_response
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Extract a JSON object from LLM response text.

        Handles LLMs that wrap JSON in markdown fences or add extra text.
        """
        text = text.strip()

        # Try to extract from markdown code fence
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()

        # If the text contains a top-level JSON object, extract just that
        first_brace = text.find("{")
        if first_brace == -1:
            raise ValueError("No JSON object found in response")

        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(text[first_brace:], start=first_brace):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    text = text[first_brace : i + 1]
                    break

        return json.loads(text)
