"""Advanced OS Toolkit — resource monitoring, process control, clipboard."""

from __future__ import annotations

import psutil
import pyperclip
import asyncio
import os
import subprocess
import shutil
import webbrowser

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

    # In-memory clipboard history (survives within session).
    _history: list[str] = []
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
                if text and (not self._history or self._history[-1] != text):
                    self._history.append(text)
                    if len(self._history) > self._MAX_HISTORY:
                        self._history = self._history[-self._MAX_HISTORY :]
                return self._success(
                    "Clipboard stored to history",
                    data={"entries": len(self._history), "latest": text[:200]},
                )

            if action in ("list", "history"):
                recent = self._history[-10:] if self._history else []
                entries = [
                    {"index": len(self._history) - len(recent) + i, "preview": e[:100]}
                    for i, e in enumerate(recent)
                ]
                return self._success(
                    f"Clipboard history ({len(self._history)} total)",
                    data={"entries": entries},
                )

            if action in ("restore", "get", "recall"):
                if index is None:
                    return self._failure("index is required for restore action")
                idx = int(index)
                if idx < 0 or idx >= len(self._history):
                    return self._failure(f"Index {idx} out of range (0-{len(self._history) - 1})")
                text = self._history[idx]
                await asyncio.to_thread(pyperclip.copy, text)
                return self._success(
                    f"Restored entry {idx} to clipboard",
                    data={"text": text[:200]},
                )

            if action == "clear":
                self._history.clear()
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
                return self._success("Opened YouTube video", data={"url": url})
            except Exception as exc:
                return self._failure(str(exc))

        # Otherwise construct a YouTube search URL and open it.
        import urllib.parse

        search_url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        )
        try:
            await asyncio.to_thread(webbrowser.open_new_tab, search_url)
            return self._success(
                f"Opened YouTube search for '{query}'",
                data={"url": search_url, "query": query},
            )
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
        "$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]; "
        "$mgr = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult(); "
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
