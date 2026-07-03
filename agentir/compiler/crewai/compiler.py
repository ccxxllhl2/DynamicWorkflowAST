"""CrewAI Workflow Compiler.

Compiles AgentIR WorkflowDefinitions into CrewAI Python code.

CrewAI uses Agents, Tasks, and Crews:
    - Each agent becomes a CrewAI Agent with role/goal/backstory
    - Each tool becomes a CrewAI Tool
    - Sequence → Process.sequential with ordered Tasks
    - Parallel → Multiple Crews or async execution
    - Condition → Task with conditional logic
    - Loop → Iterative task execution
    - SubWorkflow → Nested Crew

Output is a runnable ``crew.kickoff()`` call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agentir.compiler.base import BaseCompiler, CompilationResult
from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import (
    AgentNode,
    ConditionNode,
    LoopNode,
    ParallelNode,
    SequenceNode,
    SubWorkflowNode,
    ToolNode,
    WorkflowNode,
)
from agentir.llm.config import AgentConfig


# ---- Tree Walkers ----

def _collect_agents(node: WorkflowNode) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    def _walk(n: WorkflowNode) -> None:
        if isinstance(n, AgentNode):
            if n.agent not in seen:
                seen.add(n.agent)
                result.append(n.agent)
        elif isinstance(n, SequenceNode):
            for step in n.steps:
                _walk(step)
        elif isinstance(n, ParallelNode):
            for branch in n.branches:
                _walk(branch)
        elif isinstance(n, ConditionNode):
            _walk(n.true_branch)
            _walk(n.false_branch)
        elif isinstance(n, LoopNode):
            _walk(n.body)
        elif isinstance(n, (ToolNode, SubWorkflowNode)):
            pass

    _walk(node)
    return result


def _collect_agent_instructions(node: WorkflowNode) -> dict[str, str]:
    """Collect per-node instructions for each agent."""
    instructions: dict[str, str] = {}

    def _walk(n: WorkflowNode) -> None:
        if isinstance(n, AgentNode):
            if n.agent not in instructions and n.instruction:
                instructions[n.agent] = n.instruction
        elif isinstance(n, SequenceNode):
            for step in n.steps:
                _walk(step)
        elif isinstance(n, ParallelNode):
            for branch in n.branches:
                _walk(branch)
        elif isinstance(n, ConditionNode):
            _walk(n.true_branch)
            _walk(n.false_branch)
        elif isinstance(n, LoopNode):
            _walk(n.body)

    _walk(node)
    return instructions


def _collect_tools(node: WorkflowNode) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    def _walk(n: WorkflowNode) -> None:
        if isinstance(n, ToolNode):
            if n.tool not in seen:
                seen.add(n.tool)
                result.append(n.tool)
        elif isinstance(n, SequenceNode):
            for step in n.steps:
                _walk(step)
        elif isinstance(n, ParallelNode):
            for branch in n.branches:
                _walk(branch)
        elif isinstance(n, ConditionNode):
            _walk(n.true_branch)
            _walk(n.false_branch)
        elif isinstance(n, LoopNode):
            _walk(n.body)
        elif isinstance(n, (AgentNode, SubWorkflowNode)):
            pass

    _walk(node)
    return result


def _flatten_tasks(node: WorkflowNode) -> list[dict]:
    """Flatten the IR tree into an ordered list of task descriptions.
    Returns a list of {agent, description, condition, loop_count} dicts.
    """
    tasks: list[dict] = []

    def _walk(n: WorkflowNode) -> None:
        if isinstance(n, AgentNode):
            tasks.append({"agent": n.agent, "description": f"Execute {n.agent} task"})
        elif isinstance(n, ToolNode):
            tasks.append({"agent": None, "tool": n.tool, "description": f"Execute tool: {n.tool}"})
        elif isinstance(n, SequenceNode):
            for step in n.steps:
                _walk(step)
        elif isinstance(n, ParallelNode):
            tasks.append({"agent": None, "parallel": True, "branches": len(n.branches)})
            for branch in n.branches:
                _walk(branch)
            tasks.append({"agent": None, "parallel_end": True})
        elif isinstance(n, ConditionNode):
            tasks.append({"agent": None, "condition": n.expression, "description": f"Evaluate: {n.expression}"})
            _walk(n.true_branch)
            tasks.append({"agent": None, "condition_end": True})
            tasks.append({"agent": None, "else_branch": True, "description": "Alternative path"})
            _walk(n.false_branch)
        elif isinstance(n, LoopNode):
            tasks.append({"agent": None, "loop_start": n.max_iterations, "description": f"Loop (max {n.max_iterations})"})
            _walk(n.body)
            tasks.append({"agent": None, "loop_end": True})
        elif isinstance(n, SubWorkflowNode):
            tasks.append({"agent": None, "subworkflow": n.workflow, "description": f"Sub-workflow: {n.workflow}"})

    _walk(node)
    return tasks


# ---- Code Generator ----

def _generate_crewai_code(
    workflow: WorkflowDefinition,
    agent_configs: dict[str, AgentConfig] | None = None,
) -> str:
    agent_configs = agent_configs or {}
    lines: list[str] = []
    sep = "# " + "=" * 60

    lines.append("# Generated by AgentIR CrewAI Compiler v0.1.0")
    lines.append("# Target: CrewAI (https://docs.crewai.com/)")
    lines.append("")
    lines.append("from crewai import Agent, Task, Crew, Process")
    lines.append("")

    agent_names = _collect_agents(workflow.root)
    agent_instructions = _collect_agent_instructions(workflow.root)
    tool_names = _collect_tools(workflow.root)

    # Agent definitions
    lines.append(sep)
    lines.append("# Agent Definitions")
    lines.append(sep)
    lines.append("")

    for agent_name in agent_names:
        cfg = agent_configs.get(agent_name)
        role = agent_name.replace("_", " ").title()
        goal = f"Complete {agent_name} tasks effectively"
        backstory = (
            agent_instructions.get(agent_name)
            or (cfg.instruction if cfg and cfg.instruction else f"Expert {agent_name} specialist")
        )
        lines.append(f"# Agent: {agent_name}")
        lines.append(f"{agent_name} = Agent(")
        lines.append(f'    role="{role}",')
        lines.append(f'    goal="{goal}",')
        lines.append(f'    backstory="{backstory}",')
        lines.append("    allow_delegation=False,")
        if cfg and cfg.model:
            lines.append(f'    llm="{cfg.model}",')
        lines.append(")")
        lines.append("")

    # Tool definitions
    if tool_names:
        lines.append(sep)
        lines.append("# Tool Definitions")
        lines.append(sep)
        lines.append("")
        for tool_name in tool_names:
            lines.append(f"# Tool: {tool_name}")
            lines.append(f"# TODO: Implement {tool_name} tool")
            lines.append(f"{tool_name}_tool = None  # Replace with actual CrewAI Tool")
            lines.append("")

    # Task generation from flattened tree
    tasks = _flatten_tasks(workflow.root)

    lines.append(sep)
    lines.append("# Task Definitions")
    lines.append(sep)
    lines.append("")

    task_names: list[str] = []
    task_counter = [0]
    prev_agent: str | None = None

    for i, t in enumerate(tasks):
        task_counter[0] += 1
        tid = f"task_{task_counter[0]}"

        if t.get("agent"):
            agent_var = t["agent"]
            desc = t.get("description", f"Execute {agent_var}")
            lines.append(f"# Task: {agent_var}")
            lines.append(f"{tid} = Task(")
            lines.append(f'    description="{desc}",')
            lines.append(f'    expected_output="Result from {agent_var}",')
            lines.append(f"    agent={agent_var},")
            if prev_agent and prev_agent != agent_var:
                lines.append(f"    context=[{task_names[-1]}],")
            lines.append(")")
            lines.append("")
            task_names.append(tid)
            prev_agent = agent_var

        elif t.get("tool"):
            tool_var = t["tool"]
            lines.append(f"# Tool task: {tool_var}")
            lines.append(f"{tid} = Task(")
            lines.append(f'    description="Execute tool: {tool_var}",')
            lines.append(f'    expected_output="Tool result",')
            lines.append(f"    agent={agent_names[0] if agent_names else 'None'},")
            if tool_names:
                lines.append(f"    tools=[{tool_var}_tool],")
            lines.append(")")
            lines.append("")
            task_names.append(tid)

        elif t.get("condition"):
            lines.append(f"# Condition: {t['condition']}")
            lines.append(f"# (Conditional branching — use if/else in task logic)")

        elif t.get("loop_start"):
            lines.append(f"# Loop start (max {t['loop_start']} iterations)")
            lines.append(f"# (Use max_execution_time or callback for loop control)")

        elif t.get("subworkflow"):
            lines.append(f"# Sub-workflow: {t['subworkflow']}")
            lines.append(f"# TODO: Create nested crew for {t['subworkflow']}")

    # Crew assembly
    lines.append(sep)
    lines.append("# Crew Assembly")
    lines.append(sep)
    lines.append("")

    all_agents = ", ".join(agent_names) if agent_names else "[]"
    all_tasks = ", ".join(task_names) if task_names else "[]"

    lines.append("crew = Crew(")
    lines.append(f"    agents=[{all_agents}],")
    lines.append(f"    tasks=[{all_tasks}],")
    lines.append("    process=Process.sequential,")
    lines.append("    verbose=True,")
    lines.append(")")
    lines.append("")

    lines.append(sep)
    lines.append("# Execution")
    lines.append(sep)
    lines.append("")
    lines.append("# result = crew.kickoff()")
    lines.append("# print(result)")
    lines.append("")

    return "\n".join(lines)


# ---- CrewAI Compiler ----

@dataclass
class CrewAICompiler(BaseCompiler):
    """Compiles AgentIR workflows to CrewAI Python code.

    Usage:
        result = CrewAICompiler().compile(workflow)
        print(result.source_code)
    """

    runtime: str = "crewai"

    def compile(
        self,
        workflow: WorkflowDefinition,
        agent_configs: dict[str, AgentConfig] | None = None,
        **kwargs: object,
    ) -> CompilationResult:
        try:
            source_code = _generate_crewai_code(workflow, agent_configs=agent_configs)
            return CompilationResult(
                success=True,
                source_code=source_code,
                runtime=self.runtime,
            )
        except Exception as e:
            return CompilationResult(
                success=False,
                errors=[str(e)],
                runtime=self.runtime,
            )
