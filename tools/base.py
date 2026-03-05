"""Abstract base class that every OmniCore tool must implement.

This ensures a uniform interface for the Cognitive Router to invoke any
tool without knowing its internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from models.tools import ToolInput, ToolOutput, ToolStatus


class BaseTool(ABC):
    """Contract that all OmniCore tools must fulfil.

    Subclasses must set ``name`` and ``description`` as class attributes
    and implement the ``execute`` method.  Optionally set
    ``is_destructive = True`` for tools that modify external state.
    """

    # Subclasses override these as plain class attributes.
    name: str = ""
    description: str = ""
    is_destructive: bool = False

    @abstractmethod
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        """Run the tool with the given parameters and return a result."""

    def requires_approval(self, tool_input: ToolInput) -> bool:
        """Return True if this invocation should trigger HITL approval."""
        return self.is_destructive

    # -- convenience helpers ---------------------------------------------------

    def _success(self, result: str, data: dict | None = None) -> ToolOutput:
        return ToolOutput(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            result=result,
            data=data or {},
        )

    def _failure(self, error: str) -> ToolOutput:
        return ToolOutput(
            tool_name=self.name,
            status=ToolStatus.FAILURE,
            error=error,
        )


def resolve_user_path(path_str: str, sandbox_root: Path) -> tuple[Path, bool]:
    """Resolve a user path to a concrete path and flag cross-boundary access.

    Returns (path, is_cross_boundary). Cross-boundary means the resolved path
    is outside the sandbox root (including smart paths like Desktop).
    """
    sandbox = sandbox_root.resolve()
    raw = (path_str or "").strip()
    normalized = raw.replace("\\", "/")

    # Smart alias: Desktop
    if normalized.lower() == "desktop" or normalized.lower().startswith("desktop/"):
        remainder = normalized[7:].lstrip("/")
        target = (Path.home() / "Desktop" / remainder).resolve()
        return target, True

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        target = candidate.resolve()
        return target, not str(target).startswith(str(sandbox))

    target = (sandbox / raw).resolve()
    return target, not str(target).startswith(str(sandbox))
