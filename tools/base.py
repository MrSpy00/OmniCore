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
import winreg
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


def resolve_user_path(path_str: str) -> tuple[Path, bool]:
    """Resolve a user path directly on the host OS.

    Absolute paths are allowed as-is. Relative paths resolve against the real
    Windows user profile directory. The second tuple item is retained for
    backwards compatibility and is always ``False``.
    """
    home = _host_user_home()
    special = _windows_special_folders()
    desktop = special.get("desktop") or (home / "Desktop")
    downloads = special.get("downloads") or (home / "Downloads")
    documents = special.get("documents") or (home / "Documents")

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
        # Map placeholder C:\Users\<Username> to dynamic home root.
        if remainder:
            remainder_norm = remainder.replace("\\", "/")
            lower = remainder_norm.lower()
            if lower == "desktop":
                return desktop.resolve(), False
            if lower.startswith("desktop/"):
                return (desktop / remainder_norm[len("desktop/") :]).resolve(), False
            if lower == "downloads":
                return downloads.resolve(), False
            if lower.startswith("downloads/"):
                return (downloads / remainder_norm[len("downloads/") :]).resolve(), False
            if lower in {"documents", "personal"}:
                return documents.resolve(), False
            if lower.startswith("documents/"):
                return (documents / remainder_norm[len("documents/") :]).resolve(), False
        return home.resolve(), False

    raw = raw.replace("<Username>", home.name).replace("<username>", home.name)
    normalized = raw.replace("\\", "/")

    alias_map = {
        "desktop": desktop,
        "downloads": downloads,
        "documents": documents,
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
    """Resolve host home from USERPROFILE/HOMEDRIVE+HOMEPATH/Path.home."""
    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        return Path(userprofile).expanduser().resolve()

    homedrive = (os.environ.get("HOMEDRIVE") or "").strip()
    homepath = (os.environ.get("HOMEPATH") or "").strip()
    if homedrive and homepath:
        return Path(f"{homedrive}{homepath}").expanduser().resolve()

    return Path.home().expanduser().resolve()


def _windows_special_folders() -> dict[str, Path]:
    """Resolve Desktop/Documents/Downloads from User Shell Folders registry.

    Handles OneDrive relocation and non-English Windows folder names.
    """
    home = _host_user_home()
    paths: dict[str, Path] = {}
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    value_map = {
        "desktop": "Desktop",
        "documents": "Personal",
        "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    }

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            for alias, value_name in value_map.items():
                try:
                    raw_value, _ = winreg.QueryValueEx(key, value_name)
                except OSError:
                    continue
                expanded = os.path.expandvars(str(raw_value)).replace("%USERPROFILE%", str(home))
                if expanded.strip():
                    paths[alias] = Path(expanded).expanduser().resolve()
    except OSError:
        pass

    return paths


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
