"""Base compiler interface and shared types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from agentir.ir.models import WorkflowDefinition


@dataclass
class CompilationResult:
    """Result of compiling a WorkflowDefinition to a target runtime.

    Attributes:
        success: Whether compilation succeeded.
        source_code: The generated source code (if successful).
        errors: List of compilation errors.
        runtime: Target runtime name (e.g., "adk").
    """

    success: bool
    source_code: str = ""
    errors: list[str] = field(default_factory=list)
    runtime: str = ""

    @property
    def code(self) -> str:
        """Alias for source_code."""
        return self.source_code


class BaseCompiler(ABC):
    """Abstract base for all runtime compilers.

    Subclasses implement compile() to convert a WorkflowDefinition
    into runtime-specific code.
    """

    @abstractmethod
    def compile(self, workflow: WorkflowDefinition, **kwargs) -> CompilationResult:
        """Compile a workflow to this compiler's target runtime."""
        ...
