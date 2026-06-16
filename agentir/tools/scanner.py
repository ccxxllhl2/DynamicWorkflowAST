"""AST-based tool scanner.

Parses Python source files to extract tool metadata without executing them.
Looks for an ``async def execute(...)`` function and extracts:

- Function name (always ``execute``)
- Parameter names and type annotations (via AST)
- Return type annotation
- Docstring (first line used as description)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ToolInfo:
    """Metadata for a discovered tool."""

    name: str  # derived from filename (without .py)
    path: str  # absolute path to the .py file
    function: str = "execute"  # the entry-point function name
    description: str = ""  # extracted from docstring or registry
    input_params: dict[str, str] = field(default_factory=dict)  # param_name → type_annotation
    output_type: str = ""  # return type annotation

    @classmethod
    def from_file(cls, filepath: Path) -> ToolInfo | None:
        """Scan a Python file and extract tool metadata via AST.

        Args:
            filepath: Path to a .py file in the tools directory.

        Returns:
            ToolInfo if an ``async def execute`` function is found, else None.
        """
        try:
            source = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None

        tool_name = filepath.stem  # filename without .py

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute":
                info = ToolInfo(
                    name=tool_name,
                    path=str(filepath.resolve()),
                    function="execute",
                )

                # Extract docstring
                doc = ast.get_docstring(node)
                if doc:
                    # Use first non-empty line as description
                    first_line = doc.strip().split("\n")[0].strip()
                    info.description = first_line

                # Extract parameter type annotations
                for arg in node.args.args:
                    if arg.arg in ("self", "cls"):
                        continue
                    anno = cls._unparse_annotation(arg.annotation)
                    info.input_params[arg.arg] = anno

                # Extract return type
                info.output_type = cls._unparse_annotation(node.returns)

                return info

        return None

    @staticmethod
    def _unparse_annotation(node: ast.expr | None) -> str:
        """Convert an AST annotation node back to a source string."""
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Subscript):
            # Handle types like list[str], dict[str, int]
            base = ToolInfo._unparse_annotation(node.value)
            if isinstance(node.slice, ast.Tuple):
                args = ", ".join(
                    ToolInfo._unparse_annotation(e)
                    for e in node.slice.elts
                )
            else:
                args = ToolInfo._unparse_annotation(node.slice)
            return f"{base}[{args}]"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Union types: str | None
            left = ToolInfo._unparse_annotation(node.left)
            right = ToolInfo._unparse_annotation(node.right)
            return f"{left} | {right}"
        # Fallback: return the raw source segment
        try:
            import ast as _ast
            return ast.unparse(node)
        except Exception:
            return ""
