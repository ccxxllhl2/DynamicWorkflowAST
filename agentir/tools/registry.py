"""Tool registry — discovers, loads, and queries user-defined tools.

Supports two modes:
1. **Auto-scan** (``from_directory()``): walks a directory tree, parses each
   ``.py`` file with the AST scanner, and builds a registry from discovered
   ``async def execute()`` functions.
2. **Manual YAML** (``from_yaml()``): loads tool metadata from a YAML file,
   useful for adding descriptions, aliases, or custom input schemas beyond
   what AST parsing can infer.

The two modes can be combined: scan for tools, then merge in a YAML overlay
to enrich descriptions or override parameter schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agentir.tools.scanner import ToolInfo


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, trying PyYAML first, then a minimal parser."""
    try:
        import yaml  # type: ignore[import-untyped]

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback: read as JSON (YAML is a superset; simple cases work)
        raw = path.read_text(encoding="utf-8")
        # Very basic YAML → dict for simple registry files
        return _parse_simple_yaml(raw)


def _parse_simple_yaml(raw: str) -> dict:
    """Minimal YAML parser for simple tool registry files (no PyYAML needed)."""
    result: dict = {}
    current_section: str | None = None
    current_list: list[dict] = []
    current_item: dict | None = None
    current_key: str | None = None

    for line in raw.splitlines():
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0:
            # Top-level key
            if ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip()
                if val:
                    result[key] = val.strip('"').strip("'")
                else:
                    current_section = key
                    current_list = []
                    result[key] = current_list
                current_item = None
                current_key = None
        elif indent == 2 and current_section and stripped.startswith("- "):
            # List item
            current_item = {}
            current_list.append(current_item)
            key_val = stripped[2:]
            if ":" in key_val:
                k, _, v = key_val.partition(":")
                current_item[k.strip()] = v.strip().strip('"').strip("'")
        elif indent == 4 and current_item is not None:
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                current_item[k.strip()] = v.strip().strip('"').strip("'")

    return result


def scan_file(filepath: Path) -> ToolInfo | None:
    """Public alias for scanning a single file. (Re-exported for convenience.)"""
    return ToolInfo.from_file(filepath)


@dataclass
class ToolRegistry:
    """In-memory registry of available tools.

    Tools are indexed by name and can be queried for Planner context,
    Validator checks, and Compiler code generation.
    """

    tools: dict[str, ToolInfo] = field(default_factory=dict)

    # ---- Factory Methods ----

    @classmethod
    def from_directory(cls, directory: str | Path) -> ToolRegistry:
        """Scan a directory tree and build a registry from discovered tools.

        Only ``.py`` files containing an ``async def execute(...)`` function
        are registered. Files without this function are silently skipped.
        """
        registry = cls()
        root = Path(directory).resolve()
        if not root.is_dir():
            return registry

        for py_file in sorted(root.rglob("*.py")):
            # Skip __init__.py and hidden files
            if py_file.name.startswith("_") or py_file.name.startswith("."):
                continue
            info = ToolInfo.from_file(py_file)
            if info:
                # If a YAML registry file exists, enrich the info
                yaml_path = root / "registry.yaml"
                if yaml_path.is_file():
                    _apply_yaml_overlay(info, yaml_path)
                registry.tools[info.name] = info

        return registry

    @classmethod
    def from_yaml(cls, yaml_path: str | Path, tools_dir: str | Path = ".") -> ToolRegistry:
        """Load tool metadata from a YAML registry file, optionally auto-scanning.

        The YAML should have a ``tools`` key with a list of tool entries:
        ```yaml
        tools:
          - name: web_search
            path: tools/web_search.py
            function: execute
            description: Search the web for information.
        ```

        If a tool's ``path`` is given, the scanner extracts parameter info from
        the source file. Otherwise, only the YAML metadata is used.
        """
        registry = cls()
        yaml_path = Path(yaml_path).resolve()
        if not yaml_path.is_file():
            return registry

        data = _load_yaml(yaml_path)
        tool_list = data.get("tools", [])

        tools_root = Path(tools_dir).resolve()

        for entry in tool_list:
            name = entry.get("name", "")
            if not name:
                continue

            info = ToolInfo(
                name=name,
                path=entry.get("path", ""),
                function=entry.get("function", "execute"),
                description=entry.get("description", ""),
            )

            # Enrich with AST scanner if source file exists
            src_path = tools_root / info.path if info.path else None
            if src_path and not src_path.is_absolute():
                src_path = tools_root / src_path
            if src_path and src_path.is_file():
                scanned = ToolInfo.from_file(src_path)
                if scanned:
                    # Merge: YAML takes priority for description
                    if not info.description and scanned.description:
                        info.description = scanned.description
                    info.input_params = scanned.input_params
                    info.output_type = scanned.output_type

            registry.tools[name] = info

        return registry

    @classmethod
    def empty(cls) -> ToolRegistry:
        """Create an empty registry (no tools available)."""
        return cls()

    # ---- Query Methods ----

    def has(self, name: str) -> bool:
        """Check whether a tool is registered."""
        return name in self.tools

    def get(self, name: str) -> ToolInfo | None:
        """Get tool metadata by name."""
        return self.tools.get(name)

    def list_tools(self) -> list[ToolInfo]:
        """Return all registered tools, sorted by name."""
        return sorted(self.tools.values(), key=lambda t: t.name)

    def to_prompt_context(self) -> str:
        """Build a human-readable tool listing for the Planner system prompt."""
        if not self.tools:
            return "No custom tools available."

        lines: list[str] = []
        for info in self.list_tools():
            params = ", ".join(
                f"{k}: {v}" if v else k for k, v in info.input_params.items()
            )
            sig = f"{info.function}({params})"
            ret = f" -> {info.output_type}" if info.output_type else ""
            desc = f" — {info.description}" if info.description else ""
            lines.append(f"- {info.name} ({sig}{ret}){desc}")

        return "\n".join(lines)


def _apply_yaml_overlay(info: ToolInfo, yaml_path: Path) -> None:
    """Enrich a ToolInfo with metadata from a YAML registry file, if present."""
    try:
        data = _load_yaml(yaml_path)
    except Exception:
        return

    tool_list = data.get("tools", [])
    for entry in tool_list:
        if entry.get("name") == info.name:
            if entry.get("description") and not info.description:
                info.description = entry["description"]
            if entry.get("function"):
                info.function = entry["function"]
            break
