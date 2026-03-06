"""Advanced OS Toolkit — resource monitoring, process control, clipboard."""

from __future__ import annotations

import psutil
import pyperclip
import asyncio
import subprocess
import shutil

from typing import cast

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


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
        app = str(
            self._first_param(
                params,
                "app",
                "application",
                "name",
                "program",
                "query",
                "target",
                "value",
                default="",
            )
        )
        if not app:
            return self._failure("app is required")

        try:
            await asyncio.to_thread(_launch_windows_app, app)
            return self._success(f"Launch request sent for {app}")
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
            return self._success("Now playing detected", data=result)
        except Exception as exc:
            return self._failure(str(exc))


def _collect_resource_info() -> dict[str, float]:
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_used_percent": psutil.virtual_memory().percent,
        "disk_used_percent": psutil.disk_usage("/").percent,
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
    app_lower = app.strip().lower()

    uri_map = {
        "spotify": "spotify:",
        "teams": "msteams:",
        "steam": "steam://open/main",
    }
    if app_lower in uri_map:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", f"Start-Process '{uri_map[app_lower]}'"],
            shell=False,
        )
        return

    if shutil.which(app):
        subprocess.Popen([app], shell=False)
        return

    # Shell apps folder fallback (UWP).
    command = (
        "$pkg = Get-StartApps | Where-Object { $_.Name -like '*"
        + app
        + "*' } | Select-Object -First 1; "
        'if ($pkg) { Start-Process "shell:AppsFolder\\$($pkg.AppID)" } '
        "else { throw 'App not found' }"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", command], shell=False)


def _get_now_playing_powershell() -> dict[str, str]:
    script = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime; "
        "$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]; "
        "$mgr = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult(); "
        "$session = $mgr.GetCurrentSession(); "
        "if (-not $session) { exit 1 }; "
        "$props = $session.TryGetMediaPropertiesAsync().GetAwaiter().GetResult(); "
        "$out = @{title=$props.Title; artist=$props.Artist; album=$props.AlbumTitle}; "
        "$out | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=8,
    )
    if completed.returncode != 0:
        return {}
    raw = completed.stdout.strip()
    if not raw:
        return {}
    import json

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    return {
        "title": str(parsed.get("title", "")),
        "artist": str(parsed.get("artist", "")),
        "album": str(parsed.get("album", "")),
    }
