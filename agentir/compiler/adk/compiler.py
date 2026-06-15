"""ADK 2.0 Workflow Compiler.

Compiles AgentIR WorkflowDefinitions into Google ADK 2.0 Workflow Runtime code.

The compilation process:
    1. Walk the tree IR, flattening into a graph of nodes + edges
    2. Assign unique IDs to agent occurrences
    3. Decompose compound nodes (Sequence, Parallel, Condition, Loop)
       into edges with helper nodes (fork, join, cond, counter)
    4. Generate clean Python source code
"""

from __future__ import annotations

import textwrap
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
    WorkflowNode,
)


# ---- Intermediate Graph Representation ----


@dataclass
class FlatNode:
    """A node in the flattened ADK graph."""

    id: str
    kind: Literal["agent", "fork", "join", "condition", "loop_counter", "terminal"]
    agent_name: str = ""  # for 'agent' kind
    expression: str = ""  # for 'condition' kind
    max_iterations: int = 0  # for 'loop_counter' kind


@dataclass
class FlatEdge:
    """An edge in the flattened ADK graph."""

    from_id: str
    to_id: str
    route: str = ""  # "true" or "false" for conditional routing


@dataclass
class FlatGraph:
    """Flattened intermediate graph ready for code generation."""

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


# ---- Tree → Graph Flattener ----


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

    else:
        raise ValueError(f"Unknown node type: {type(node)}")


# ---- Code Generator ----


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


def _generate_python_code(graph: FlatGraph) -> str:
    """Generate ADK 2.0 Python source code from a flat graph."""
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

    for agent_name in agent_names:
        lines.append(f'# Agent: {agent_name}')
        lines.append(f'{agent_name} = LlmAgent(')
        lines.append(f'    name="{agent_name}",')
        lines.append(f'    model="gemini-2.0-flash",  # TODO: configure')
        lines.append(f'    instruction="You are the {agent_name} agent.",  # TODO: configure')
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


# ---- ADK Compiler ----


@dataclass
class ADKCompiler(BaseCompiler):
    """Compiles AgentIR workflows to Google ADK 2.0 Workflow code."""

    runtime: str = "adk"

    def compile(
        self,
        workflow: WorkflowDefinition,
        **kwargs: object,
    ) -> CompilationResult:
        """Compile a WorkflowDefinition to ADK 2.0 Python source code.

        Args:
            workflow: The validated AgentIR workflow.
            **kwargs: Reserved for future options.

        Returns:
            CompilationResult with the generated Python source code.
        """
        try:
            graph = FlatGraph()

            # Build the flattened graph
            terminal_id = graph.get_terminal_id()
            exit_id = _flatten_node(workflow.root, graph, "__START__")
            graph.add_edge(exit_id, terminal_id)

            # Generate Python code
            source_code = _generate_python_code(graph)

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
