"""ADK 2.0 Workflow Compiler.

Compiles AgentIR WorkflowDefinitions into Google ADK 2.0 Workflow Runtime code.

The compilation process follows the ADK Dynamic Workflows pattern:
    1. Walk the tree IR to collect all agent names
    2. Generate LlmAgent definitions for each unique agent
    3. Generate a main @node(rerun_on_resume=True) orchestration function
       that uses ctx.run_node() to invoke agents in sequence/parallel/conditional/loop
    4. Generate sub-@node functions for parallel branches
    5. Generate the Workflow constructor with a single edge: (START, main_workflow)

    Reference: https://adk.dev/graphs/dynamic/

Agent configuration injection:
    Pass agent_configs to compile() to set per-agent model, instruction,
    tools, and temperature in the generated code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from agentir.compiler.base import BaseCompiler, CompilationResult
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
from agentir.llm.config import AgentConfig


# ---- Intermediate Graph Representation (Legacy - kept for tests) ----


@dataclass
class FlatNode:
    """A node in the flattened ADK graph (legacy static-graph model)."""

    id: str
    kind: Literal["agent", "fork", "join", "condition", "loop_counter", "terminal"]
    agent_name: str = ""  # for 'agent' kind
    expression: str = ""  # for 'condition' kind
    max_iterations: int = 0  # for 'loop_counter' kind


@dataclass
class FlatEdge:
    """An edge in the flattened ADK graph (legacy static-graph model)."""

    from_id: str
    to_id: str
    route: str = ""  # "true" or "false" for conditional routing


@dataclass
class FlatGraph:
    """Flattened intermediate graph ready for code generation (legacy)."""

    nodes: dict[str, FlatNode] = field(default_factory=dict)
    edges: list[FlatEdge] = field(default_factory=list)
    agent_counter: int = 0
    helper_counter: int = 0

    def add_agent(self, agent_name: str) -> str:
        """Register an agent occurrence and return its unique ID."""
        self.agent_counter += 1
        node_id = f"{agent_name}_{self.agent_counter}"
        self.nodes[node_id] = FlatNode(
            id=node_id,
            kind="agent",
            agent_name=agent_name,
        )
        return node_id

    def add_edge(self, from_id: str, to_id: str, route: str = "") -> None:
        self.edges.append(FlatEdge(from_id=from_id, to_id=to_id, route=route))

    def add_helper(self, kind: str, **kwargs: object) -> str:
        """Add a helper node and return its ID."""
        self.helper_counter += 1
        node_id = f"{kind}_{self.helper_counter}"
        self.nodes[node_id] = FlatNode(id=node_id, kind=kind, **kwargs)  # type: ignore[arg-type]
        return node_id

    def get_terminal_id(self) -> str:
        """Get or create the terminal node."""
        if "__TERMINAL__" not in self.nodes:
            self.nodes["__TERMINAL__"] = FlatNode(id="__TERMINAL__", kind="terminal")
        return "__TERMINAL__"


# ---- Tree → Graph Flattener (Legacy) ----


def _flatten_node(
    node: WorkflowNode,
    graph: FlatGraph,
    entry_id: str,
) -> str:
    """Flatten a workflow node into the graph.

    Connects from `entry_id` into the subgraph and returns the exit node ID.
    """
    if isinstance(node, AgentNode):
        agent_id = graph.add_agent(node.agent)
        graph.add_edge(entry_id, agent_id)
        return agent_id

    elif isinstance(node, SequenceNode):
        current = entry_id
        for step in node.steps:
            current = _flatten_node(step, graph, current)
        return current

    elif isinstance(node, ParallelNode):
        fork_id = graph.add_helper("fork")
        join_id = graph.add_helper("join")
        terminal_id = graph.get_terminal_id()

        graph.add_edge(entry_id, fork_id)

        branch_exits: list[str] = []
        for branch in node.branches:
            exit_id = _flatten_node(branch, graph, fork_id)
            branch_exits.append(exit_id)

        for exit_id in branch_exits:
            graph.add_edge(exit_id, join_id)

        return join_id

    elif isinstance(node, ConditionNode):
        cond_id = graph.add_helper("condition", expression=node.expression)

        graph.add_edge(entry_id, cond_id)

        true_exit = _flatten_node(node.true_branch, graph, cond_id)
        false_exit = _flatten_node(node.false_branch, graph, cond_id)

        # Mark the conditional edges
        # Replace the last edges from cond_id with routed versions
        graph.edges = [
            e for e in graph.edges
            if not (e.from_id == cond_id and e.route == "")
        ]
        graph.add_edge(cond_id, true_exit, route="true")
        graph.add_edge(cond_id, false_exit, route="false")

        # Merge point after condition
        merge_id = graph.add_helper("join")
        graph.add_edge(true_exit, merge_id)
        graph.add_edge(false_exit, merge_id)
        return merge_id

    elif isinstance(node, LoopNode):
        counter_id = graph.add_helper(
            "loop_counter", max_iterations=node.max_iterations
        )
        exit_id = graph.add_helper("join")

        graph.add_edge(entry_id, counter_id)

        # Body entry point (counter routes here on "continue")
        body_entry = graph.add_helper("join")
        body_exit = _flatten_node(node.body, graph, body_entry)

        # Loop routing:
        #   counter → body_entry [continue]  (enter body)
        #   counter → exit_id [done]         (exit loop)
        #   body_exit → counter              (loop back)
        graph.add_edge(counter_id, body_entry, route="continue")
        graph.add_edge(counter_id, exit_id, route="done")
        graph.add_edge(body_exit, counter_id)

        return exit_id

    elif isinstance(node, ToolNode):
        # Tools are handled as leaf helper nodes in legacy mode
        tool_id = graph.add_helper("fork")  # reuse fork as generic tool placeholder
        graph.add_edge(entry_id, tool_id)
        return tool_id

    else:
        raise ValueError(f"Unknown node type: {type(node)}")


# ---- Legacy Static Graph Code Generator (kept for unit tests) ----


def _make_node_ref(graph: FlatGraph) -> dict[str, str]:
    """Build a mapping from node_id → Python variable reference.

    - Agent nodes: reference their agent_name (the LlmAgent variable)
    - Helper nodes: reference their node_id (the @node function name)
    - __START__: references 'START'
    - __TERMINAL__: references 'None'
    """
    refs: dict[str, str] = {}
    refs["__START__"] = "START"
    refs["__TERMINAL__"] = "None"

    for node in graph.nodes.values():
        if node.kind == "agent":
            # Use agent_name as the Python variable name
            refs[node.id] = node.agent_name
        elif node.kind == "terminal":
            pass  # Already set to "None" above
        else:
            refs[node.id] = node.id

    return refs


def _generate_python_code(
    graph: FlatGraph,
    agent_configs: dict[str, AgentConfig] | None = None,
    default_model: str = "gemini-2.0-flash",
    default_instruction_template: str = "You are the {agent_name} agent.",
) -> str:
    """Generate ADK 2.0 Python source code from a flat graph (legacy static-graph format).

    Args:
        graph: The flattened workflow graph.
        agent_configs: Optional per-agent configuration (model, instruction, tools, temp).
        default_model: Fallback model when no agent_config is provided.
        default_instruction_template: Fallback instruction template.
    """
    lines: list[str] = []
    refs = _make_node_ref(graph)

    # Header
    lines.append('# Generated by AgentIR ADK Compiler v0.1.0')
    lines.append('# Target: Google ADK 2.0 Workflow Runtime')
    lines.append('')
    lines.append('from google.adk.agents import LlmAgent')
    lines.append('from google.adk.workflow import Workflow, node')
    lines.append('from google.adk.workflow._graph import START')
    lines.append('')
    lines.append('')
    lines.append('# ============================================================')
    lines.append('# Agent Definitions')
    lines.append('# ============================================================')
    lines.append('')

    # Collect unique agent names (first occurrence wins)
    agent_names: dict[str, str] = {}  # agent_name → first node_id
    for node in graph.nodes.values():
        if node.kind == "agent" and node.agent_name not in agent_names:
            agent_names[node.agent_name] = node.id

    agent_configs = agent_configs or {}

    for agent_name in agent_names:
        cfg = agent_configs.get(agent_name)
        model = cfg.model if cfg and cfg.model else default_model
        instruction = (
            cfg.instruction
            if cfg and cfg.instruction
            else default_instruction_template.format(agent_name=agent_name)
        )
        tools = cfg.tools if cfg else []
        temperature = cfg.temperature if cfg else None

        lines.append(f'# Agent: {agent_name}')
        lines.append(f'{agent_name} = LlmAgent(')
        lines.append(f'    name="{agent_name}",')
        lines.append(f'    model="{model}",')
        lines.append(f'    instruction="{instruction}",')
        if tools:
            tool_list = ", ".join(tools)
            lines.append(f'    tools=[{tool_list}],')
        if temperature is not None:
            lines.append(f'    temperature={temperature},')
        lines.append(f')')
        lines.append('')

    # Agent aliases for duplicate occurrences
    for node in graph.nodes.values():
        if node.kind == "agent" and node.id not in agent_names.values():
            agent_name = node.agent_name
            lines.append(f'# Alias for duplicate occurrence of {agent_name}')
            lines.append(f'{node.id} = {agent_name}')
            # Update ref to use the alias variable if needed
            # (We keep using agent_name as the main ref, aliases are extras)
            lines.append('')

    lines.append('')
    lines.append('# ============================================================')
    lines.append('# Helper Nodes')
    lines.append('# ============================================================')
    lines.append('')

    # Define helper nodes
    for node in graph.nodes.values():
        if node.kind == "fork":
            lines.append('@node')
            lines.append(f'async def {node.id}(state: dict) -> dict:')
            lines.append('    """Parallel fan-out node."""')
            lines.append('    return state')
            lines.append('')
        elif node.kind == "join":
            lines.append('@node')
            lines.append(f'async def {node.id}(state: dict) -> dict:')
            lines.append('    """Fan-in / merge node."""')
            lines.append('    return state')
            lines.append('')
        elif node.kind == "condition":
            lines.append('@node')
            lines.append(f'async def {node.id}(state: dict) -> dict:')
            lines.append(f'    """Condition: {node.expression}"""')
            lines.append('    # TODO: Implement condition evaluation')
            lines.append(f'    # Expression: {node.expression}')
            lines.append('    result = state.get("condition_result", "false")')
            lines.append('    return {**state, "__route__": result}')
            lines.append('')
        elif node.kind == "loop_counter":
            lines.append('@node')
            lines.append(f'async def {node.id}(state: dict) -> dict:')
            lines.append(f'    """Loop counter (max {node.max_iterations} iterations)."""')
            lines.append('    count = state.get("_loop_count", 0) + 1')
            lines.append(f'    if count > {node.max_iterations}:')
            lines.append('        return {**state, "__route__": "done"}')
            lines.append('    return {**state, "_loop_count": count, "__route__": "continue"}')
            lines.append('')

    lines.append('')
    lines.append('# ============================================================')
    lines.append('# Workflow Definition')
    lines.append('# ============================================================')
    lines.append('')

    # Generate edges
    lines.append('workflow = Workflow(')
    lines.append('    edges=[')

    # Group conditional edges by source node
    cond_edges: dict[str, dict[str, list[str]]] = {}  # from_id → {route: [to_ids]}
    simple_edges: list[FlatEdge] = []

    for edge in graph.edges:
        if edge.route:
            if edge.from_id not in cond_edges:
                cond_edges[edge.from_id] = {}
            if edge.route not in cond_edges[edge.from_id]:
                cond_edges[edge.from_id][edge.route] = []
            cond_edges[edge.from_id][edge.route].append(edge.to_id)
        else:
            simple_edges.append(edge)

    # Emit simple edges
    for edge in simple_edges:
        from_ref = refs.get(edge.from_id, edge.from_id)
        to_ref = refs.get(edge.to_id, edge.to_id)
        lines.append(f'        ({from_ref}, {to_ref}),')

    # Emit conditional edges (one dict per source, all routes combined)
    for from_id, routes in cond_edges.items():
        from_ref = refs.get(from_id, from_id)
        route_parts = []
        for route, to_ids in routes.items():
            targets = ", ".join(refs.get(t, t) for t in to_ids)
            route_parts.append(f'"{route}": {targets}')
        route_map = "{ " + ", ".join(route_parts) + " }"
        lines.append(f'        ({from_ref}, {route_map}),')

    lines.append('    ],')
    lines.append(')')
    lines.append('')

    return '\n'.join(lines)


# ================================================================
# Dynamic Workflow Code Generator (@node + ctx.run_node)
# Reference: https://adk.dev/graphs/dynamic/
# ================================================================

def _collect_agents(node: WorkflowNode) -> list[str]:
    """Walk the IR tree and return agent names in encounter order, deduplicated."""
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
        elif isinstance(n, ToolNode):
            pass  # Leaf node, handled separately

    _walk(node)
    return result


def _collect_tools(node: WorkflowNode) -> list[str]:
    """Walk the IR tree and return tool names in encounter order, deduplicated."""
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
        elif isinstance(n, AgentNode):
            pass  # Not a tool

    _walk(node)
    return result


def _is_empty(node: WorkflowNode) -> bool:
    """Check if a node represents no meaningful work (empty sequence)."""
    if isinstance(node, SequenceNode):
        return len(node.steps) == 0
    return False


def _generate_orchestration_body(
    node: WorkflowNode,
    parallel_branches: list[tuple[str, WorkflowNode]],
    indent: int = 4,
) -> list[str]:
    """Recursively generate ctx.run_node() orchestration code.

    Args:
        node: The IR node to generate code for.
        parallel_branches: Accumulator for parallel branch sub-workflows.
            Each tuple is (function_name, branch_node). The caller collects
            these to generate separate @node functions later.
        indent: Current indentation level (number of spaces).

    Returns:
        List of Python source code lines for this node's orchestration body.
    """
    pad = " " * indent

    if isinstance(node, AgentNode):
        return [f"{pad}_result = await ctx.run_node({node.agent}, _result)"]

    elif isinstance(node, ToolNode):
        return [f"{pad}_result = await ctx.run_node(tool_{node.tool}, _result)"]

    elif isinstance(node, SequenceNode):
        lines: list[str] = []
        for step in node.steps:
            lines.extend(
                _generate_orchestration_body(step, parallel_branches, indent)
            )
        return lines

    elif isinstance(node, ParallelNode):
        lines = [f"{pad}# Parallel execution of {len(node.branches)} branch(es)"]
        lines.append(f"{pad}_tasks = []")
        for _i, branch in enumerate(node.branches):
            func_name = f"_branch_{len(parallel_branches)}"
            parallel_branches.append((func_name, branch))
            lines.append(f"{pad}_tasks.append(ctx.run_node({func_name}, _result))")
        lines.append(f"{pad}_results = await asyncio.gather(*_tasks)")
        lines.append(
            f"{pad}_result = _results[-1] if _results else _result"
        )
        return lines

    elif isinstance(node, ConditionNode):
        expr = node.expression
        lines = [
            f"{pad}# Condition: {expr}",
            f"{pad}# TODO: implement actual condition evaluation based on _result",
            f"{pad}if _result and _result.get('condition_result', False):",
        ]
        lines.extend(
            _generate_orchestration_body(
                node.true_branch, parallel_branches, indent + 4
            )
        )
        if not _is_empty(node.false_branch):
            lines.append(f"{pad}else:")
            lines.extend(
                _generate_orchestration_body(
                    node.false_branch, parallel_branches, indent + 4
                )
            )
        return lines

    elif isinstance(node, LoopNode):
        max_it = node.max_iterations
        lines = [
            f"{pad}_loop_count = 0",
            f"{pad}while _loop_count < {max_it}:",
            f"{pad}    _loop_count += 1",
        ]
        lines.extend(
            _generate_orchestration_body(node.body, parallel_branches, indent + 4)
        )
        return lines

    return []


def _generate_dynamic_workflow_code(
    workflow: WorkflowDefinition,
    agent_configs: dict[str, AgentConfig] | None = None,
    tools_dir: str = "./tools",
    default_model: str = "gemini-2.0-flash",
    default_instruction_template: str = "You are the {agent_name} agent.",
) -> str:
    """Generate ADK 2.0 Dynamic Workflow Python source using @node + ctx.run_node().

    Follows the official ADK dynamic workflows pattern:
    https://adk.dev/graphs/dynamic/

    Generated code structure:
        1. Imports (Context, Workflow, LlmAgent, node, asyncio if needed)
        2. Agent definitions (LlmAgent for each unique agent)
        3. Tool wrapper @node functions (import from user's tools/)
        4. Sub-@node functions for parallel branches
        5. Main @node(rerun_on_resume=True) orchestrator function
        6. Workflow constructor with (START, main_workflow) edge
    """
    agent_configs = agent_configs or {}
    lines: list[str] = []

    # ---- Header ----
    lines.append("# Generated by AgentIR ADK Compiler v0.2.0")
    lines.append("# Target: Google ADK 2.0 Dynamic Workflow Runtime")
    lines.append("# Reference: https://adk.dev/graphs/dynamic/")
    lines.append("")

    # ---- Collect agents, tools & parallel branches ----
    agent_names = _collect_agents(workflow.root)
    tool_names = _collect_tools(workflow.root)
    parallel_branches: list[tuple[str, WorkflowNode]] = []
    body_code = _generate_orchestration_body(workflow.root, parallel_branches, indent=4)

    # ---- Imports ----
    lines.append("from google.adk import Context, Workflow")
    lines.append("from google.adk.agents import LlmAgent")
    lines.append("from google.adk.workflow import node")
    if parallel_branches:
        lines.append("import asyncio")
    # Sys path setup for tool imports
    lines.append("")
    if tool_names:
        lines.append("# Ensure the tools directory is importable")
        lines.append("import sys, os")
        lines.append(f"_tools_dir = os.path.abspath('{tools_dir}')")
        lines.append('if _tools_dir not in sys.path:')
        lines.append('    sys.path.insert(0, _tools_dir)')
        lines.append("")
    lines.append("")

    # ---- Agent Definitions ----
    sep = "# " + "=" * 60
    lines.append(sep)
    lines.append("# Agent Definitions")
    lines.append(sep)
    lines.append("")

    for agent_name in agent_names:
        cfg = agent_configs.get(agent_name)
        model = cfg.model if cfg and cfg.model else default_model
        instruction = (
            cfg.instruction
            if cfg and cfg.instruction
            else default_instruction_template.format(agent_name=agent_name)
        )
        tools = cfg.tools if cfg else []
        temperature = cfg.temperature if cfg else None

        lines.append(f"# Agent: {agent_name}")
        lines.append(f"{agent_name} = LlmAgent(")
        lines.append(f'    name="{agent_name}",')
        lines.append(f'    model="{model}",')
        lines.append(f'    instruction="{instruction}",')
        if tools:
            tool_args = ", ".join(f'"{t}"' for t in tools)
            lines.append(f"    tools=[{tool_args}],")
        if temperature is not None:
            lines.append(f"    temperature={temperature},")
        lines.append(")")
        lines.append("")

    # ---- Tool Wrappers ----
    if tool_names:
        lines.append("")
        lines.append(sep)
        lines.append("# Tool Wrappers (@node functions)")
        lines.append(sep)
        lines.append("")

        for tool_name in tool_names:
            lines.append(f"# Import tool: {tool_name}")
            lines.append(f"from {tool_name} import execute as _exec_{tool_name}")
            lines.append("")
            lines.append("@node")
            lines.append(
                f"async def tool_{tool_name}(ctx: Context, _result=None):"
            )
            lines.append(f'    """Tool: {tool_name}"""')
            lines.append(
                f"    _input = str(_result) if _result else \"\""
            )
            lines.append(f"    return await _exec_{tool_name}(_input)")
            lines.append("")

    # ---- Parallel Branch Sub-Workflows ----
    if parallel_branches:
        lines.append("")
        lines.append(sep)
        lines.append("# Parallel Branch Sub-Workflows")
        lines.append(sep)
        lines.append("")

        for func_name, branch_node in parallel_branches:
            branch_body = _generate_orchestration_body(branch_node, [], indent=4)
            lines.append("@node")
            lines.append(f"async def {func_name}(ctx: Context, _result=None):")
            if not branch_body:
                lines.append("    return _result")
            else:
                lines.extend(branch_body)
                lines.append("    return _result")
            lines.append("")

    # ---- Main Orchestration Function ----
    lines.append(sep)
    lines.append("# Main Workflow Orchestrator")
    lines.append(sep)
    lines.append("")

    wf_desc = workflow.description or " → ".join(agent_names)
    lines.append("@node(rerun_on_resume=True)")
    lines.append("async def main_workflow(ctx: Context):")
    lines.append(f'    """{wf_desc}"""')
    lines.append("    _result = None  # initial input to the first node")
    if body_code:
        lines.extend(body_code)
    lines.append("    return _result")
    lines.append("")

    # ---- Workflow Constructor ----
    lines.append(sep)
    lines.append("# Workflow Definition")
    lines.append(sep)
    lines.append("")
    lines.append("workflow = Workflow(")
    lines.append(f'    name="{workflow.name}",')
    lines.append(f'    description="{wf_desc}",')
    lines.append('    edges=[("START", main_workflow)],')
    lines.append(")")
    lines.append("")

    return "\n".join(lines)


# ---- ADK Compiler ----

@dataclass
class ADKCompiler(BaseCompiler):
    """Compiles AgentIR workflows to Google ADK 2.0 Dynamic Workflow code.

    Uses the @node decorator + ctx.run_node() pattern from ADK dynamic workflows.
    Reference: https://adk.dev/graphs/dynamic/

    Supports agent configuration injection for model, instruction, tools, and temperature.

    Usage:
        from agentir.llm.config import AgentConfig

        configs = {
            "researcher": AgentConfig(
                agent_name="researcher",
                model="deepseek-chat",
                instruction="You are a research specialist.",
                temperature=0.3,
            ),
        }
        result = ADKCompiler().compile(workflow, agent_configs=configs)
    """

    runtime: str = "adk"
    default_model: str = "gemini-2.0-flash"
    default_instruction_template: str = "You are the {agent_name} agent."

    def compile(
        self,
        workflow: WorkflowDefinition,
        agent_configs: dict[str, AgentConfig] | None = None,
        tools_dir: str = "./tools",
        **kwargs: object,
    ) -> CompilationResult:
        """Compile a WorkflowDefinition to ADK 2.0 Dynamic Workflow Python source.

        Args:
            workflow: The validated AgentIR workflow.
            agent_configs: Optional per-agent configuration.
                Keys are agent names, values are AgentConfig objects with
                model, instruction, tools, and temperature.
            tools_dir: Path to the user's tools directory (for import generation).
            **kwargs: Reserved for future options.

        Returns:
            CompilationResult with the generated Python source code.
        """
        try:
            source_code = _generate_dynamic_workflow_code(
                workflow,
                agent_configs=agent_configs,
                tools_dir=tools_dir,
                default_model=self.default_model,
                default_instruction_template=self.default_instruction_template,
            )

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
