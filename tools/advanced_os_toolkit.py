"""Advanced OS Toolkit — resource monitoring, process control, clipboard."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import tempfile
import webbrowser
from pathlib import Path
from typing import cast

import psutil
import pyperclip

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, force_window_foreground, resolve_user_path


def _run_elevated_command(command: str, timeout: int = 120) -> dict[str, object]:
    system = platform.system().lower()

    if os.name == "nt":
        command_json = json.dumps(command)
        ps = (
            "Start-Process powershell "
            f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-Command',{command_json} "
            "-Verb RunAs -WindowStyle Hidden"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode == 0:
            return {
                "platform": "windows",
                "command": command,
                "backend": "powershell_start_process",
                "returncode": completed.returncode,
                "stdout": (completed.stdout or "")[:4000],
                "stderr": (completed.stderr or "")[:4000],
            }

        # Fallback: VBScript RunAs launcher for systems where Start-Process cannot elevate.
        vbs_path = Path(tempfile.gettempdir()) / "omnicore_elevated_run.vbs"
        vbs_path.write_text(
            'Set UAC = CreateObject("Shell.Application")\n'
            + (
                'UAC.ShellExecute "powershell.exe", '
                f'"-NoProfile -ExecutionPolicy Bypass -Command {command_json}", '
                '"", "runas", 0\n'
            ),
            encoding="utf-8",
        )
        try:
            vbs_run = subprocess.run(
                ["wscript", str(vbs_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "platform": "windows",
                "command": command,
                "backend": "vbs_runas_fallback",
                "returncode": vbs_run.returncode,
                "stdout": ((completed.stdout or "") + "\n" + (vbs_run.stdout or ""))[:4000],
                "stderr": ((completed.stderr or "") + "\n" + (vbs_run.stderr or ""))[:4000],
            }
        finally:
            try:
                vbs_path.unlink(missing_ok=True)
            except Exception:
                pass

    if system == "darwin":
        wrapped = f"sudo -n /bin/zsh -lc {json.dumps(command)}"
        completed = subprocess.run(
            ["/bin/zsh", "-lc", wrapped],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "platform": "macos",
            "command": wrapped,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[:4000],
            "stderr": (completed.stderr or "")[:4000],
        }

    wrapped = f"sudo -n /bin/bash -lc {json.dumps(command)}"
    completed = subprocess.run(
        ["/bin/bash", "-lc", wrapped],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "platform": "linux",
        "command": wrapped,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[:4000],
        "stderr": (completed.stderr or "")[:4000],
    }


class OsExecuteElevated(BaseTool):
    name = "os_execute_elevated"
    description = "Execute a command with admin/root elevation based on host OS."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        command = str(self._first_param(params, "command", "cmd", "value", default="")).strip()
        timeout = int(self._first_param(params, "timeout", default=120) or 120)

        if not command:
            return self._failure("command is required")

        try:
            result = await asyncio.to_thread(_run_elevated_command, command, max(10, timeout))
            returncode_raw = result.get("returncode", 1)
            returncode = int(returncode_raw) if isinstance(returncode_raw, (int, str)) else 1
            if returncode != 0:
                return self._failure(json.dumps(result, ensure_ascii=True))
            return self._success("Elevated command executed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class OsResourceMonitor(BaseTool):
    name = "os_resource_monitor"
    description = "Return current CPU, RAM, and Disk usage."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        info = await asyncio.to_thread(_collect_resource_info)
        return self._success("Resource usage collected", data=info)


class OsListRunningProcesses(BaseTool):
    name = "os_list_running_processes"
    description = "List top 15 memory-consuming processes."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        top = await asyncio.to_thread(_top_memory_processes)
        return self._success("Top processes collected", data={"processes": top})


class OsKillProcess(BaseTool):
    name = "os_kill_process"
    description = "Kill a process by PID."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        pid = self._first_param(params, "pid", "process_id", "id")
        if pid is None:
            return self._failure("pid is required")
        try:
            proc = psutil.Process(int(pid))
            await asyncio.to_thread(proc.terminate)
            return self._success(f"Terminated PID {pid}")
        except Exception as exc:
            return self._failure(str(exc))


class OsClipboardRead(BaseTool):
    name = "os_clipboard_read"
    description = "Read text from the system clipboard."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            text = await asyncio.to_thread(pyperclip.paste) or ""
            return self._success("Clipboard read", data={"text": text})
        except Exception as exc:
            return self._failure(str(exc))


class OsClipboardWrite(BaseTool):
    name = "os_clipboard_write"
    description = "Write text to the system clipboard."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        text = str(self._first_param(params, "text", "content", "value", default=""))
        try:
            await asyncio.to_thread(pyperclip.copy, text)
            return self._success("Clipboard updated", data={"length": len(text)})
        except Exception as exc:
            return self._failure(str(exc))


class OsLaunchApplication(BaseTool):
    name = "os_launch_application"
    description = "Launch desktop/UWP applications on Windows (e.g., Spotify, Steam)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        app_value = (
            params.get("app")
            or params.get("query")
            or params.get("application")
            or params.get("name")
            or params.get("program")
            or params.get("target")
            or params.get("value")
        )
        if app_value in (None, "") and params:
            app_value = next((value for value in params.values() if value not in (None, "")), "")
        app = str(app_value or "").strip()
        if not app:
            return self._failure("app is required")

        try:
            await asyncio.to_thread(_launch_windows_app, app)
            foreground = await asyncio.to_thread(force_window_foreground, app)
            return self._success(
                f"Launch request sent for {app}",
                data={"app": app, "foreground": foreground},
            )
        except Exception as exc:
            return self._failure(str(exc))


class OsGetNowPlaying(BaseTool):
    name = "os_get_now_playing"
    description = "Get currently playing media title/artist from Windows session."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            result = await asyncio.to_thread(_get_now_playing_powershell)
            if not result:
                return self._failure("No active media session found")
            title = str(result.get("title", "")).strip()
            if not title:
                return self._failure("No active media session found")
            return self._success("Now playing detected", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class OsOpenBrowserVisible(BaseTool):
    name = "os_open_browser_visible"
    description = "Open a URL in the user's real default browser in a visible tab."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", "query", "value", default=""))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            await asyncio.to_thread(webbrowser.open_new_tab, url)
            return self._success("Opened visible browser tab", data={"url": url})
        except Exception as exc:
            return self._failure(str(exc))


class OsClipboardHistoryManager(BaseTool):
    name = "os_clipboard_history_manager"
    description = (
        "Manage clipboard history: read current, store to history, list recent entries, "
        "or restore a previous entry."
    )
    is_destructive = True

    _MAX_HISTORY = 50

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", "command", default="list")).lower()
        index = self._first_param(params, "index", "entry", default=None)

        try:
            if action in ("read", "current"):
                text = await asyncio.to_thread(pyperclip.paste) or ""
                return self._success("Current clipboard", data={"text": text})

            if action in ("store", "save", "push"):
                text = await asyncio.to_thread(pyperclip.paste) or ""
                history = _clipboard_history_load()
                if text and (not history or history[-1] != text):
                    history.append(text)
                    if len(history) > self._MAX_HISTORY:
                        history = history[-self._MAX_HISTORY :]
                    _clipboard_history_save(history)
                return self._success(
                    "Clipboard stored to history",
                    data={"entries": len(history), "latest": text[:200], "source": "windows+disk"},
                )

            if action in ("list", "history"):
                history = _clipboard_history_load()
                recent = history[-10:] if history else []
                entries = [
                    {"index": len(history) - len(recent) + i, "preview": e[:100]}
                    for i, e in enumerate(recent)
                ]
                return self._success(
                    f"Clipboard history ({len(history)} total)",
                    data={"entries": entries, "source": "windows+disk"},
                )

            if action in ("restore", "get", "recall"):
                history = _clipboard_history_load()
                if index is None:
                    return self._failure("index is required for restore action")
                idx = int(index)
                if idx < 0 or idx >= len(history):
                    return self._failure(f"Index {idx} out of range (0-{len(history) - 1})")
                text = history[idx]
                await asyncio.to_thread(pyperclip.copy, text)
                return self._success(
                    f"Restored entry {idx} to clipboard",
                    data={"text": text[:200], "source": "windows+disk"},
                )

            if action == "clear":
                _clipboard_history_save([])
                return self._success("Clipboard history cleared")

            return self._failure(f"Unknown action: {action}")
        except Exception as exc:
            return self._failure(str(exc))


class WebPlayYoutubeVideoVisible(BaseTool):
    name = "web_play_youtube_video_visible"
    description = (
        "Search YouTube for a video query and open the top result in the user's "
        "real default browser. Physical browser opening is mandatory."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        query = str(
            self._first_param(
                params, "query", "search", "video", "song", "url", "value", default=""
            )
        )
        if not query:
            return self._failure("query is required")

        # If it's already a YouTube URL, open directly.
        if "youtube.com/" in query or "youtu.be/" in query:
            url = query if query.startswith("http") else f"https://{query}"
            try:
                await asyncio.to_thread(webbrowser.open_new_tab, url)
                fg = await asyncio.to_thread(force_window_foreground, "YouTube")
                return self._success("Opened YouTube video", data={"url": url, "foreground": fg})
            except Exception as exc:
                return self._failure(str(exc))

        # Otherwise construct a YouTube search URL and open it.
        import urllib.parse

        search_url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        )
        try:
            await asyncio.to_thread(webbrowser.open_new_tab, search_url)
            fg = await asyncio.to_thread(force_window_foreground, "YouTube")
            return self._success(
                f"Opened YouTube search for '{query}'",
                data={"url": search_url, "query": query, "foreground": fg},
            )
        except Exception as exc:
            return self._failure(str(exc))


class SysForceForeground(BaseTool):
    name = "sys_force_foreground"
    description = "Find a window by title and force it to foreground."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        title = str(
            self._first_param(params, "window_title", "title", "name", "target", default="")
        )
        if not title:
            return self._failure("window_title is required")
        try:
            result = await asyncio.to_thread(force_window_foreground, title)
            if not result.get("activated"):
                reason = result.get("stderr") or result.get("error") or result
                return self._failure(f"Window activation failed for '{title}': {reason}")
            return self._success("Window forced to foreground", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class SysGetAllInstalledApps(BaseTool):
    name = "sys_get_all_installed_apps"
    description = "List installed apps by querying Windows Uninstall registry keys."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            apps = await asyncio.to_thread(_list_installed_apps_from_registry)
            return self._success(
                f"Installed apps listed ({len(apps)} entries)",
                data={"count": len(apps), "apps": apps},
            )
        except Exception as exc:
            return self._failure(str(exc))


class MediaControlSpotifyNative(BaseTool):
    name = "media_control_spotify_native"
    description = "Control active Spotify/media session (play, pause, next, previous)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", "command", default="pause")).lower()
        try:
            result = await asyncio.to_thread(_media_control_native, action)
            return self._success(f"Media control action completed: {action}", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class SysReadNotifications(BaseTool):
    name = "sys_read_notifications"
    description = "Read recent Windows notifications from Event Log and app state data."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        limit = int(self._first_param(params, "limit", default=20) or 20)
        try:
            entries = await asyncio.to_thread(_read_windows_notifications, limit)
            return self._success(
                f"Read {len(entries)} notification records",
                data={
                    "notifications": entries,
                    "count": len(entries),
                    "source": "windows_eventlog",
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class SysAutoTroubleshooter(BaseTool):
    name = "sys_auto_troubleshooter"
    description = "Collect system diagnostics and suggest likely root causes for common failures."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        symptom = str(self._first_param(params, "symptom", "issue", "query", default="")).strip()
        if not symptom:
            symptom = "general system instability"

        try:
            diagnostics = await asyncio.to_thread(_collect_basic_diagnostics)
            findings = _infer_diagnostic_findings(symptom, diagnostics)
            return self._success(
                "System auto-troubleshooter completed",
                data={
                    "symptom": symptom,
                    "diagnostics": diagnostics,
                    "findings": findings,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class OsPhantomFileHider(BaseTool):
    name = "os_phantom_file_hider"
    description = "Toggle hidden attribute on a file or directory (Windows only)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if os.name != "nt":
            return self._failure("os_phantom_file_hider is supported only on Windows")

        params = self._params(tool_input)
        path_raw = str(self._first_param(params, "path", "target", "file_path", default="")).strip()
        action = str(self._first_param(params, "action", default="hide")).strip().lower()
        if not path_raw:
            return self._failure("path is required")
        if action not in {"hide", "unhide"}:
            return self._failure("action must be hide or unhide")

        try:
            target_path, _ = resolve_user_path(path_raw)
            result = await asyncio.to_thread(_toggle_hidden_attribute, target_path, action)
            return self._success(
                f"Phantom file action completed: {action}",
                data=result,
            )
        except Exception as exc:
            return self._failure(str(exc))


def _list_installed_apps_from_registry() -> list[dict[str, str]]:
    import winreg

    uninstall_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    apps: list[dict[str, str]] = []

    for hive, base in uninstall_keys:
        try:
            with winreg.OpenKey(hive, base) as key:
                subkey_count = winreg.QueryInfoKey(key)[0]
                for i in range(subkey_count):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub_name) as app_key:
                            display_name = _reg_query_str(app_key, "DisplayName")
                            if not display_name:
                                continue
                            apps.append(
                                {
                                    "name": display_name,
                                    "version": _reg_query_str(app_key, "DisplayVersion"),
                                    "publisher": _reg_query_str(app_key, "Publisher"),
                                    "install_location": _reg_query_str(app_key, "InstallLocation"),
                                    "uninstall_string": _reg_query_str(app_key, "UninstallString"),
                                }
                            )
                    except OSError:
                        continue
        except OSError:
            continue

    dedup: dict[str, dict[str, str]] = {}
    for app in apps:
        name = app.get("name", "")
        if not name:
            continue
        dedup.setdefault(name, app)
    return sorted(dedup.values(), key=lambda a: a.get("name", "").lower())


def _reg_query_str(key, value_name: str) -> str:
    import winreg

    try:
        value, _ = winreg.QueryValueEx(key, value_name)
        return str(value)
    except OSError:
        return ""


def _media_control_native(action: str) -> dict[str, str]:
    normalized = action.strip().lower()
    if normalized not in {"play", "pause", "next", "previous", "prev", "toggle"}:
        raise ValueError("Unsupported action. Use play|pause|next|previous|toggle")

    key_map = {
        "play": "[char]179",
        "pause": "[char]179",
        "toggle": "[char]179",
        "next": "[char]176",
        "previous": "[char]177",
        "prev": "[char]177",
    }
    # Primary: media key via WScript (works for active media transport session including Spotify).
    ps = f"$ws = New-Object -ComObject WScript.Shell; $ws.SendKeys({key_map[normalized]}); 'ok'"
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "media control failed").strip())

    # Optional pycaw touch: ensure endpoint device is reachable for native session context.
    try:
        from pycaw.pycaw import AudioUtilities  # type: ignore[import-not-found]

        _ = AudioUtilities.GetAllSessions()
    except Exception:
        pass

    return {
        "action": normalized,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }


def _clipboard_history_file() -> Path:
    base = resolve_user_path(r"%USERPROFILE%\AppData\Local\OmniCore")[0]
    base.mkdir(parents=True, exist_ok=True)
    return base / "clipboard_history.json"


def _clipboard_history_load() -> list[str]:
    # Always include current clipboard at tail if unique.
    file_path = _clipboard_history_file()
    history: list[str] = []
    if file_path.exists() and file_path.is_file():
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                history = [str(v) for v in payload if isinstance(v, str)]
        except Exception:
            history = []

    try:
        current = pyperclip.paste() or ""
        if current and (not history or history[-1] != current):
            history.append(current)
    except Exception:
        pass

    if len(history) > OsClipboardHistoryManager._MAX_HISTORY:
        history = history[-OsClipboardHistoryManager._MAX_HISTORY :]
    return history


def _clipboard_history_save(history: list[str]) -> None:
    file_path = _clipboard_history_file()
    file_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_windows_notifications(limit: int) -> list[dict[str, str]]:
    ps = (
        "$limit = " + str(max(1, limit)) + "; "
        "Get-WinEvent -LogName 'Microsoft-Windows-PushNotifications-Platform/Operational' "
        "-MaxEvents $limit | "
        "Select-Object TimeCreated, Id, LevelDisplayName, Message | "
        "ConvertTo-Json -Depth 4"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stderr or completed.stdout or "notification read failed").strip()
        )

    raw = (completed.stdout or "").strip()
    if not raw:
        return []

    parsed = json.loads(raw)
    rows = parsed if isinstance(parsed, list) else [parsed]
    result: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "time": str(row.get("TimeCreated", "")),
                "id": str(row.get("Id", "")),
                "level": str(row.get("LevelDisplayName", "")),
                "message": str(row.get("Message", "")),
            }
        )
    return result


def _collect_resource_info() -> dict[str, float]:
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_used_percent": psutil.virtual_memory().percent,
        "disk_used_percent": psutil.disk_usage("/").percent,
    }


def _collect_basic_diagnostics() -> dict[str, object]:
    vm = psutil.virtual_memory()
    du = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.3)

    top = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_percent"]):
        info = proc.info
        top.append(
            {
                "pid": int(info.get("pid") or 0),
                "name": str(info.get("name") or ""),
                "cpu_percent": _to_float(info.get("cpu_percent"), 0.0),
                "memory_percent": _to_float(info.get("memory_percent"), 0.0),
            }
        )
    top.sort(key=lambda row: (row["cpu_percent"], row["memory_percent"]), reverse=True)
    return {
        "platform": platform.platform(),
        "cpu_percent": cpu,
        "memory_used_percent": vm.percent,
        "disk_used_percent": du.percent,
        "top_processes": top[:10],
    }


def _infer_diagnostic_findings(
    symptom: str, diagnostics: dict[str, object]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    cpu = _to_float(diagnostics.get("cpu_percent"), 0.0)
    mem = _to_float(diagnostics.get("memory_used_percent"), 0.0)
    disk = _to_float(diagnostics.get("disk_used_percent"), 0.0)
    symptom_l = symptom.lower()

    if cpu >= 85.0:
        findings.append(
            {
                "severity": "high",
                "cause": "High CPU saturation",
                "suggestion": "Close or restart top CPU processes and retry.",
            }
        )
    if mem >= 90.0:
        findings.append(
            {
                "severity": "high",
                "cause": "Memory pressure",
                "suggestion": "Free RAM by closing heavy apps or rebooting.",
            }
        )
    if disk >= 92.0:
        findings.append(
            {
                "severity": "high",
                "cause": "Disk nearly full",
                "suggestion": "Free disk space and rerun the failed operation.",
            }
        )

    if "network" in symptom_l or "internet" in symptom_l:
        findings.append(
            {
                "severity": "medium",
                "cause": "Network-related symptom reported",
                "suggestion": "Run net_intercept_and_analyze for connection-level diagnostics.",
            }
        )

    if not findings:
        findings.append(
            {
                "severity": "low",
                "cause": "No obvious system bottleneck detected",
                "suggestion": "Collect app-specific logs and retry with elevated diagnostics.",
            }
        )
    return findings


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _toggle_hidden_attribute(target_path: Path, action: str) -> dict[str, object]:
    if not target_path.exists():
        raise FileNotFoundError(f"Path does not exist: {target_path}")

    cmd = ["attrib", "+h" if action == "hide" else "-h", str(target_path)]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "attrib failed").strip())

    return {
        "path": str(target_path),
        "action": action,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }


def _top_memory_processes() -> list[dict[str, int | str]]:
    processes: list[dict[str, int | str]] = []
    for proc in psutil.process_iter(attrs=["pid", "name", "memory_info"]):
        info = proc.info
        mem = info.get("memory_info")
        rss = mem.rss if mem else 0
        pid = int(info.get("pid") or 0)
        name = str(info.get("name") or "")
        processes.append({"pid": pid, "name": name, "rss": rss})

    processes.sort(key=lambda p: int(cast(int, p["rss"])), reverse=True)
    return processes[:15]


def _launch_windows_app(app: str) -> None:
    """Launch a Windows application using os.system('start ...') as primary strategy.

    This approach is more reliable for UWP/Store apps than subprocess.Popen.
    Falls back to PowerShell Get-StartApps search if simple start fails.
    """
    app_lower = app.strip().lower()

    uri_map = {
        "spotify": "spotify:",
        "teams": "msteams:",
        "steam": "steam://open/main",
        "calculator": "calculator:",
        "mail": "outlookmail:",
        "calendar": "outlookcal:",
        "photos": "ms-photos:",
        "settings": "ms-settings:",
        "store": "ms-windows-store:",
        "xbox": "xbox:",
        "maps": "bingmaps:",
        "camera": "microsoft.windows.camera:",
        "clock": "ms-clock:",
        "weather": "bingweather:",
    }

    # 1. Try URI scheme via os.system('start ...') — most reliable for UWP.
    uri = uri_map.get(app_lower)
    if uri:
        exit_code = os.system(f'start "" "{uri}"')
        if exit_code == 0:
            return

    # 2. Try direct start command (works for exe-based apps).
    exit_code = os.system(f'start "" "{app}"')
    if exit_code == 0:
        return

    # 3. Try shutil.which for PATH-accessible executables.
    try:
        if shutil.which(app):
            os.system(f'start "" "{app}"')
            return
    except Exception:
        pass

    # 4. PowerShell Get-StartApps fallback for UWP apps not in uri_map.
    command = (
        "$pkg = Get-StartApps | Where-Object { $_.Name -like '*"
        + app
        + "*' } | Select-Object -First 1; "
        'if ($pkg) { Start-Process "shell:AppsFolder\\$($pkg.AppID)" } '
        "else { throw 'Uygulama bulunamadi: " + app + "' }"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", command], shell=False)


def _get_now_playing_powershell() -> dict[str, str]:
    """Get currently playing media info.

    Strategy 1: Windows Media Transport Controls (SMTC) API via PowerShell.
    Strategy 2: Fallback to scanning window titles of known media players.
    """
    # --- Strategy 1: SMTC API ---
    script = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$null = [Windows.Media.Control."
        "GlobalSystemMediaTransportControlsSessionManager, "
        "Windows.Media.Control, ContentType=WindowsRuntime]; "
        "$mgr = [Windows.Media.Control."
        "GlobalSystemMediaTransportControlsSessionManager]::"
        "RequestAsync().GetAwaiter().GetResult(); "
        "$session = $mgr.GetCurrentSession(); "
        "if (-not $session) { exit 1 }; "
        "$props = $session.TryGetMediaPropertiesAsync().GetAwaiter().GetResult(); "
        "$out = @{title=$props.Title; artist=$props.Artist; album=$props.AlbumTitle}; "
        "$out | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if completed.returncode == 0:
            raw = completed.stdout.strip()
            if raw:
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, dict) and parsed.get("title"):
                    return {
                        "title": str(parsed.get("title", "")),
                        "artist": str(parsed.get("artist", "")),
                        "album": str(parsed.get("album", "")),
                        "source": "smtc",
                    }
    except Exception:
        pass

    # --- Strategy 2: Window title scanning fallback ---
    media_apps = {
        "spotify": "Spotify",
        "vlc": "VLC media player",
        "musicbee": "MusicBee",
        "foobar2000": "foobar2000",
        "chrome": "YouTube",
        "firefox": "YouTube",
        "msedge": "YouTube",
        "wmplayer": "Windows Media Player",
        "groove": "Groove Music",
    }
    title_script = (
        "Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | "
        "Select-Object ProcessName, MainWindowTitle | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", title_script],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if completed.returncode == 0:
            raw = completed.stdout.strip()
            if raw:
                import json

                windows = json.loads(raw)
                if isinstance(windows, dict):
                    windows = [windows]
                for win in windows:
                    proc_name = str(win.get("ProcessName", "")).lower()
                    title = str(win.get("MainWindowTitle", ""))
                    if not title:
                        continue
                    for app_key in media_apps:
                        if app_key in proc_name:
                            # Extract artist - title pattern common in media players
                            if " - " in title:
                                parts = title.split(" - ", 1)
                                return {
                                    "title": parts[-1].strip(),
                                    "artist": parts[0].strip(),
                                    "album": "",
                                    "source": f"window_title:{proc_name}",
                                }
                            return {
                                "title": title,
                                "artist": "",
                                "album": "",
                                "source": f"window_title:{proc_name}",
                            }
    except Exception:
        pass

    return {}
