"""AgentIR Agent Scanner — AST-based agent definition discovery.

Parses Python files in an ``agents/`` directory and extracts agent metadata
without executing them. By convention, each agent file defines:

- ``name`` (str): the agent identifier
- ``instruction`` (str): the system prompt / instruction
- ``model`` (str, optional): the model to use
- ``temperature`` (float, optional): sampling temperature
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentDef:
    """Metadata for a pre-defined agent."""

    name: str
    instruction: str = ""
    model: str = ""
    temperature: float | None = None
    path: str = ""

    @classmethod
    def from_file(cls, filepath: Path) -> AgentDef | None:
        """Parse an agent definition from a Python file.

        Looks for top-level module assignments:
            name = "researcher"
            instruction = "You are a researcher."
            model = "deepseek-chat"       # optional
            temperature = 0.3             # optional

        Args:
            filepath: Path to a .py file in the agents directory.

        Returns:
            AgentDef if ``name`` is found, else None.
        """
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        agent_name = filepath.stem  # fallback: filename without .py
        instruction = ""
        model = ""
        temperature: float | None = None

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "name":
                        agent_name = cls._eval_literal(node.value)
                    elif target.id == "instruction":
                        instruction = cls._eval_literal(node.value)
                    elif target.id == "model":
                        model = cls._eval_literal(node.value)
                    elif target.id == "temperature":
                        val = cls._eval_literal(node.value)
                        if isinstance(val, (int, float)):
                            temperature = float(val)

        if not instruction:
            return None  # instruction is required

        return cls(
            name=agent_name,
            instruction=instruction,
            model=model,
            temperature=temperature,
            path=str(filepath.resolve()),
        )

    @staticmethod
    def _eval_literal(node: ast.expr) -> str:
        """Safely evaluate a Python literal AST node."""
        if isinstance(node, ast.Constant):
            return str(node.value) if node.value is not None else ""
        if isinstance(node, ast.JoinedStr):  # f-string
            parts = []
            for val in node.values:
                if isinstance(val, ast.Constant):
                    parts.append(str(val.value))
                else:
                    parts.append("...")
            return "".join(parts)
        return ""
