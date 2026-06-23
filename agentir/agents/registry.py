"""Agent registry — discovers pre-defined agents from the agents/ directory.

Symmetrical to the tools registry pattern. Agents are discovered via AST scanning,
indexed by name, and injected into Planner + Compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agentir.agents.scanner import AgentDef


@dataclass
class AgentRegistry:
    """In-memory registry of pre-defined agents."""

    agents: dict[str, AgentDef] = field(default_factory=dict)

    @classmethod
    def from_directory(cls, directory: str | Path) -> AgentRegistry:
        """Scan an ``agents/`` directory for agent definition files.

        Each ``.py`` file that defines a valid ``instruction`` global
        is registered as an available agent.
        """
        registry = cls()
        root = Path(directory).resolve()
        if not root.is_dir():
            return registry

        for py_file in sorted(root.rglob("*.py")):
            if py_file.name.startswith("_") or py_file.name.startswith("."):
                continue
            ag = AgentDef.from_file(py_file)
            if ag and ag.instruction:
                registry.agents[ag.name] = ag

        return registry

    @classmethod
    def empty(cls) -> AgentRegistry:
        return cls()

    def has(self, name: str) -> bool:
        return name in self.agents

    def get(self, name: str) -> AgentDef | None:
        return self.agents.get(name)

    def list_names(self) -> list[str]:
        return sorted(self.agents.keys())

    def to_prompt_context(self) -> str:
        """Build a human-readable listing for the Planner system prompt."""
        if not self.agents:
            return "(No pre-defined agents available. Create agent names freely.)"

        lines: list[str] = []
        for name in sorted(self.agents):
            ag = self.agents[name]
            desc = ag.instruction[:80] + ("..." if len(ag.instruction) > 80 else "")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def to_agent_configs(self, default_model: str = "") -> dict[str, "AgentConfig"]:
        """Convert the registry to compiler-ready AgentConfig dict."""
        from agentir.llm.config import AgentConfig

        configs: dict[str, AgentConfig] = {}
        for name, ag in self.agents.items():
            configs[name] = AgentConfig(
                agent_name=name,
                model=ag.model or default_model,
                instruction=ag.instruction,
                temperature=ag.temperature,
            )
        return configs
