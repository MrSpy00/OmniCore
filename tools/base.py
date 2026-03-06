"""Abstract base class that every OmniCore tool must implement.

This ensures a uniform interface for the Cognitive Router to invoke any
tool without knowing its internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
from pathlib import Path
from typing import Any

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

    def _params(self, tool_input: ToolInput) -> dict[str, Any]:
        value = tool_input.parameters
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"value": value, "path": value, "file_path": value, "text": value}
        return {}

    def _first_param(self, params: dict[str, Any], *names: str, default: Any = None) -> Any:
        for name in names:
            value = params.get(name)
            if value not in (None, ""):
                return value
        return default


def resolve_user_path(path_str: str, sandbox_root: Path) -> tuple[Path, bool]:
    """Resolve a user path to a concrete path and flag cross-boundary access.

    Returns (path, is_cross_boundary). Cross-boundary means the resolved path
    is outside the sandbox root (including smart paths like Desktop).
    """
    sandbox = sandbox_root.resolve()
    raw = (path_str or "").strip()
    normalized = raw.replace("\\", "/")

    home = os.path.expanduser("~")
    alias_map = {
        "desktop": os.path.join(home, "Desktop"),
        "downloads": os.path.join(home, "Downloads"),
        "documents": os.path.join(home, "Documents"),
    }
    for alias, base_path in alias_map.items():
        if normalized.lower() == alias or normalized.lower().startswith(f"{alias}/"):
            remainder = normalized[len(alias) :].lstrip("/")
            target = Path(os.path.join(base_path, remainder)).resolve()
            return target, True

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        target = candidate.resolve()
        return target, not str(target).startswith(str(sandbox))

    target = (sandbox / raw).resolve()
    return target, not str(target).startswith(str(sandbox))
