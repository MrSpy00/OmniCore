"""Abstract base class that every OmniCore tool must implement.

This ensures a uniform interface for the Cognitive Router to invoke any
tool without knowing its internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
import json
import re
import subprocess
import time
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
            data={"raw_error": error},
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


def resolve_user_path(path_str: str, sandbox_root: Path | None = None) -> tuple[Path, bool]:
    """Resolve a user path directly on the host OS.

    Absolute paths are allowed as-is. Relative paths resolve against the real
    Windows user profile directory. The second tuple item is retained for
    backwards compatibility and is always ``False``.
    """
    del sandbox_root

    home = _host_user_home()
    raw = (path_str or "").strip()
    if raw in {"", "."}:
        return home, False

    raw = os.path.expandvars(raw)
    normalized_original = raw.replace("\\", "/")
    placeholder_match = re.match(
        r"^[a-z]:/users/<username>(?:/(.*))?$", normalized_original.lower()
    )
    if placeholder_match:
        remainder = placeholder_match.group(1) or ""
        return (home / remainder).resolve(), False

    raw = raw.replace("<Username>", home.name).replace("<username>", home.name)
    normalized = raw.replace("\\", "/")

    alias_map = {
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
    }
    for alias, base_path in alias_map.items():
        alias_prefix = f"{alias}/"
        if normalized.lower() == alias:
            return base_path.resolve(), False
        if normalized.lower().startswith(alias_prefix):
            remainder = normalized[len(alias_prefix) :]
            return (base_path / remainder).resolve(), False

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve(), False

    return (home / raw).resolve(), False


def _host_user_home() -> Path:
    """Resolve host home, honoring USERPROFILE first for testability."""
    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        return Path(userprofile).expanduser().resolve()

    username = (os.environ.get("USERNAME") or "").strip()
    if username:
        candidate = Path(f"C:/Users/{username}")
        if candidate.exists():
            return candidate.resolve()

    if username:
        return Path(f"C:/Users/{username}").resolve()

    return Path.home().expanduser().resolve()


def force_window_foreground(window_title: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
    """Try to bring a window matching title to absolute foreground."""
    title_hint = (window_title or "").strip()
    if not title_hint:
        return {"activated": False, "method": "none", "error": "window_title is required"}

    last_error = ""

    try:
        import pygetwindow as gw  # type: ignore[import-not-found]

        deadline = time.time() + max(0.1, timeout_seconds)
        while time.time() < deadline:
            try:
                matches = []
                for win in gw.getAllWindows():
                    title = str(getattr(win, "title", "") or "")
                    if title and title_hint.lower() in title.lower():
                        matches.append(win)

                if matches:
                    target = matches[0]
                    matched_title = str(getattr(target, "title", "") or "")
                    try:
                        if bool(getattr(target, "isMinimized", False)):
                            target.restore()
                    except Exception:
                        pass
                    target.activate()
                    time.sleep(0.15)
                    return {
                        "activated": True,
                        "method": "pygetwindow",
                        "matched_title": matched_title,
                    }
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.2)
    except Exception as exc:
        last_error = str(exc)

    escaped = title_hint.replace("'", "''")
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"if ($ws.AppActivate('{escaped}')) {{ 'true' }} else {{ 'false' }}"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        activated = "true" in (completed.stdout or "").lower()
        return {
            "activated": activated,
            "method": "powershell_appactivate",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
            "last_error": last_error,
        }
    except Exception as exc:
        return {
            "activated": False,
            "method": "powershell_appactivate",
            "error": str(exc),
            "last_error": last_error,
        }
