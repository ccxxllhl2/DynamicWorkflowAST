"""AgentIR Tools — user-defined Python tools as workflow nodes.

Tools are Python scripts placed in a ``tools/`` directory. By convention,
each tool file exposes an ``async def execute(...)`` function. The system
discovers tools via AST scanning and maintains a registry that the Planner
and Compiler use to:

- Inject available tools into the LLM system prompt
- Generate @node wrapper functions for tool invocation in ADK workflows
- Validate that ToolNode references point to registered tools

Usage::

    from agentir.tools import ToolRegistry

    registry = ToolRegistry.from_directory("./tools")
    print(registry.list_tools())  # -> [ToolInfo(name="web_search", ...)]
"""

from agentir.tools.registry import ToolInfo, ToolRegistry

__all__ = ["ToolInfo", "ToolRegistry"]
