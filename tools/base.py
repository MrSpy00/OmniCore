"""Abstract base class that every OmniCore tool must implement.

This ensures a uniform interface for the Cognitive Router to invoke any
tool without knowing its internals.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    import winreg  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - non-Windows runtimes
    winreg = None  # type: ignore[assignment]

from models.tools import ToolInput, ToolOutput, ToolStatus
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()


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

    def _paged_text_data(
        self,
        *,
        text: str,
        offset: int = 0,
        limit: int = 4000,
        key: str = "content",
    ) -> dict[str, Any]:
        safe_text = text or ""
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, int(limit or 1))

        total = len(safe_text)
        end = min(total, safe_offset + safe_limit)
        sliced = safe_text[safe_offset:end]

        return {
            key: sliced,
            "view_range": {
                "start": safe_offset,
                "end": end,
                "total": total,
                "truncated": end < total,
            },
        }

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

    - Any absolute path is preserved as-is (e.g. ``D:\\Games``, ``E:\\Backups``,
      ``/etc``, ``/var/log``).
    - Relative paths resolve against the real host home directory.
    - On Windows, Desktop/Documents/Downloads aliases and ``<Username>``
      placeholders are expanded using dynamic shell-folder resolution.

    The second tuple item is retained for backwards compatibility and is
    always ``False``.
    """
    home = _host_user_home()
    special = _windows_special_folders() if _is_windows() else {}
    desktop = special.get("desktop") or (home / "Desktop")
    downloads = special.get("downloads") or (home / "Downloads")
    documents = special.get("documents") or (home / "Documents")

    raw = (path_str or "").strip()
    if raw in {"", "."}:
        return home, False

    raw = os.path.expandvars(raw)
    if _is_windows():
        normalized_original = raw.replace("\\", "/")
        placeholder_path = _expand_windows_user_placeholder(
            normalized_original,
            home=home,
            desktop=desktop,
            downloads=downloads,
            documents=documents,
        )
        if placeholder_path is not None:
            return placeholder_path.resolve(), False

    raw = raw.replace("<Username>", home.name).replace("<username>", home.name)

    if _is_windows() and re.fullmatch(r"[a-zA-Z]:", raw):
        return Path(f"{raw}\\").resolve(), False

    candidate = Path(raw).expanduser()
    if candidate.is_absolute() or os.path.isabs(raw):
        return candidate.resolve(), False

    normalized = raw.replace("\\", "/")

    alias_path = _resolve_alias_path(
        normalized,
        desktop=desktop,
        downloads=downloads,
        documents=documents,
    )
    if alias_path is not None:
        return alias_path.resolve(), False

    return (home / raw).resolve(), False


def _is_windows() -> bool:
    return _RUNTIME.is_windows


def _resolve_alias_path(
    normalized: str,
    *,
    desktop: Path,
    downloads: Path,
    documents: Path,
) -> Path | None:
    alias_map = {
        "desktop": desktop,
        "downloads": downloads,
        "documents": documents,
    }
    lower_normalized = normalized.lower()
    for alias, base_path in alias_map.items():
        alias_prefix = f"{alias}/"
        if lower_normalized == alias:
            return base_path
        if lower_normalized.startswith(alias_prefix):
            remainder = normalized[len(alias_prefix) :]
            return base_path / remainder
    return None


def _expand_windows_user_placeholder(
    normalized_original: str,
    *,
    home: Path,
    desktop: Path,
    downloads: Path,
    documents: Path,
) -> Path | None:
    placeholder_match = re.match(
        r"^[a-z]:/users/<username>(?:/(.*))?$", normalized_original.lower()
    )
    if not placeholder_match:
        return None

    remainder = placeholder_match.group(1) or ""
    if not remainder:
        return home

    remainder_norm = remainder.replace("\\", "/")
    lower = remainder_norm.lower()
    if lower == "desktop":
        return desktop
    if lower.startswith("desktop/"):
        return desktop / remainder_norm[len("desktop/") :]
    if lower == "downloads":
        return downloads
    if lower.startswith("downloads/"):
        return downloads / remainder_norm[len("downloads/") :]
    if lower in {"documents", "personal"}:
        return documents
    if lower.startswith("documents/"):
        return documents / remainder_norm[len("documents/") :]
    return home


def _host_user_home() -> Path:
    """Resolve host home from USERPROFILE/HOMEDRIVE+HOMEPATH/Path.home."""
    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        return Path(userprofile).expanduser().resolve()

    home = (os.environ.get("HOME") or "").strip()
    if home:
        return Path(home).expanduser().resolve()

    homedrive = (os.environ.get("HOMEDRIVE") or "").strip()
    homepath = (os.environ.get("HOMEPATH") or "").strip()
    if homedrive and homepath:
        return Path(f"{homedrive}{homepath}").expanduser().resolve()

    return Path.home().expanduser().resolve()


def _windows_special_folders() -> dict[str, Path]:
    """Resolve Desktop/Documents/Downloads from User Shell Folders registry.

    Handles OneDrive relocation and non-English Windows folder names.
    """
    if not _is_windows() or winreg is None:
        return {}

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

    # Primary (Windows): C# user32 injection through PowerShell.
    if _is_windows():
        native = _force_window_foreground_windows_native(title_hint, timeout_seconds)
        if bool(native.get("activated")):
            return native
        last_error = str(native.get("error") or native.get("stderr") or "")

    pygetwindow_result = _try_activate_with_pygetwindow(title_hint, timeout_seconds)
    if bool(pygetwindow_result.get("activated")):
        return pygetwindow_result
    if pygetwindow_result.get("error"):
        last_error = str(pygetwindow_result.get("error"))

    return _powershell_appactivate(title_hint, last_error)


def _try_activate_with_pygetwindow(window_title: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        import pygetwindow as gw  # type: ignore[import-not-found]
    except Exception as exc:
        return {"activated": False, "method": "pygetwindow", "error": str(exc)}

    deadline = time.time() + max(0.1, timeout_seconds)
    last_error = ""
    while time.time() < deadline:
        try:
            matches = []
            for win in gw.getAllWindows():
                title = str(getattr(win, "title", "") or "")
                if title and window_title.lower() in title.lower():
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

    return {"activated": False, "method": "pygetwindow", "error": last_error}


def _powershell_appactivate(window_title: str, last_error: str) -> dict[str, Any]:
    escaped = window_title.replace("'", "''")
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


def _force_window_foreground_windows_native(
    title_hint: str, timeout_seconds: float
) -> dict[str, Any]:
    escaped = title_hint.replace("'", "''")
    timeout_ms = int(max(0.1, timeout_seconds) * 1000)

    csharp = (
        "using System;\n"
        "using System.Runtime.InteropServices;\n"
        "public static class WinApi {\n"
        '  [DllImport("user32.dll")]\n'
        "  public static extern bool SetForegroundWindow(IntPtr hWnd);\n"
        '  [DllImport("user32.dll")]\n'
        "  public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);\n"
        '  [DllImport("user32.dll")]\n'
        "  public static extern IntPtr GetForegroundWindow();\n"
        "}\n"
    )

    script = (
        "$ErrorActionPreference='Stop'; "
        + "Add-Type -TypeDefinition @'\n"
        + csharp
        + "'@ -Language CSharp; "
        + f"$needle='{escaped}'; $deadline=(Get-Date).AddMilliseconds({timeout_ms}); "
        + "$proc=$null; "
        + "while((Get-Date) -lt $deadline){ "
        + "$proc = Get-Process | Where-Object { "
        + "$_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like ('*' + $needle + '*') "
        + "} | Select-Object -First 1; "
        + "if($proc){ break }; Start-Sleep -Milliseconds 120 } "
        + "if(-not $proc){ "
        + "$out=[PSCustomObject]@{activated=$false;method='powershell_user32';"
        + "error='window_not_found'}; $out|ConvertTo-Json -Compress; exit 2 } "
        + "$h=[IntPtr]$proc.MainWindowHandle; "
        + "[WinApi]::ShowWindowAsync($h,9) | Out-Null; Start-Sleep -Milliseconds 60; "
        + "$ok=[WinApi]::SetForegroundWindow($h); "
        + "$active=[WinApi]::GetForegroundWindow(); "
        + "$activated=($active -eq $h) -or $ok; "
        + "$out=[PSCustomObject]@{"
        + "activated=[bool]$activated;method='powershell_user32';"
        + "matched_title=$proc.MainWindowTitle;process=$proc.ProcessName;pid=$proc.Id}; "
        + "$out|ConvertTo-Json -Compress"
    )

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=max(10, int(timeout_seconds + 5)),
        )
    except Exception as exc:
        return {
            "activated": False,
            "method": "powershell_user32",
            "error": str(exc),
        }

    stdout = (completed.stdout or "").strip()
    if stdout:
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                parsed.setdefault("returncode", completed.returncode)
                parsed.setdefault("stderr", completed.stderr)
                return parsed
        except Exception:
            pass

    return {
        "activated": completed.returncode == 0,
        "method": "powershell_user32",
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }
