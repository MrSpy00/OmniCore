"""Advanced OS Toolkit — resource monitoring, process control, clipboard."""

from __future__ import annotations

import psutil
import pyperclip
import asyncio

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
        pid = tool_input.parameters.get("pid")
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
        text = tool_input.parameters.get("text", "")
        try:
            await asyncio.to_thread(pyperclip.copy, text)
            return self._success("Clipboard updated", data={"length": len(text)})
        except Exception as exc:
            return self._failure(str(exc))


def _collect_resource_info() -> dict[str, float]:
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_used_percent": psutil.virtual_memory().percent,
        "disk_used_percent": psutil.disk_usage("/").percent,
    }


def _top_memory_processes() -> list[dict[str, object]]:
    processes: list[dict[str, object]] = []
    for proc in psutil.process_iter(attrs=["pid", "name", "memory_info"]):
        info = proc.info
        mem = info.get("memory_info")
        rss = mem.rss if mem else 0
        pid = int(info.get("pid") or 0)
        name = str(info.get("name") or "")
        processes.append({"pid": pid, "name": name, "rss": rss})

    processes.sort(key=lambda p: int(p["rss"]), reverse=True)
    return processes[:15]
