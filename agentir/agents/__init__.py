"""AgentIR Agents — pre-defined agent definitions.

Agents are Python files in the ``agents/`` directory. Each file defines
at minimum a ``name`` and ``instruction`` (system prompt).

Usage::

    from agentir.agents import AgentRegistry

    registry = AgentRegistry.from_directory("./agents")
    print(registry.list_names())  # -> ['analyst', 'researcher']
"""

from agentir.agents.registry import AgentRegistry
from agentir.agents.scanner import AgentDef

__all__ = ["AgentRegistry", "AgentDef"]
