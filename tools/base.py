"""Abstract base class that every OmniCore tool must implement.

This ensures a uniform interface for the Cognitive Router to invoke any
tool without knowing its internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
import json
import re
from pathlib import Path
from typing import Any, Iterable

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
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                parsed = None
            return {
                "value": value,
                "query": value,
                "path": value,
                "file_path": value,
                "content": value,
                "command": value,
            }
        return {}

    def _first_param(self, params: dict[str, Any], *names: str, default: Any = None) -> Any:
        return fuzzy_get(params, names, default=default)


def fuzzy_get(params: dict[str, Any], possible_keys: Iterable[str], default: Any = None) -> Any:
    """Return the first non-empty value from possible key variations."""
    if not isinstance(params, dict):
        return default

    # Exact lookup first.
    for key in possible_keys:
        value = params.get(key)
        if value not in (None, ""):
            return value

    # Case-insensitive and normalized lookup.
    normalized_map: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(key, str):
            normalized_map[key.lower().replace("-", "_")] = value

    for key in possible_keys:
        lookup = key.lower().replace("-", "_")
        value = normalized_map.get(lookup)
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

        # Catch common bad absolute patterns like X:\desktop from LLM output.
        pattern = rf"^[a-z]:/{alias}(?:/.*)?$"
        if re.match(pattern, normalized.lower()):
            suffix = normalized.split(f"/{alias}", 1)[1].lstrip("/")
            target = Path(os.path.join(base_path, suffix)).resolve()
            return target, True

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        target = candidate.resolve()
        return target, not str(target).startswith(str(sandbox))

    target = (sandbox / raw).resolve()
    return target, not str(target).startswith(str(sandbox))
