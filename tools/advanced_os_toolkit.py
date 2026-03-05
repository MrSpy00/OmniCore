"""Advanced OS Toolkit — process control, app launching, clipboard access."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import pyperclip

from config.logging import get_logger
from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

logger = get_logger(__name__)


def _resolve_sandboxed(path_str: str) -> Path:
    """Resolve *path_str* within the sandbox root. Raises on escape."""
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


class OsListRunningProcesses(BaseTool):
    name = "os_list_running_processes"
    description = "List currently running processes (name, pid)."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            import psutil

            limit = int(tool_input.parameters.get("limit", 100))
            processes = []
            for proc in psutil.process_iter(attrs=["pid", "name"]):
                info = proc.info
                processes.append({"pid": info.get("pid"), "name": info.get("name")})
                if len(processes) >= limit:
                    break
            logger.info("os.process_list", count=len(processes))
            return self._success(
                f"Listed {len(processes)} running processes",
                data={"processes": processes},
            )
        except ImportError:
            return self._failure("psutil is required for process listing")
        except Exception as exc:
            return self._failure(str(exc))


class OsKillProcess(BaseTool):
    name = "os_kill_process"
    description = "Kill a process by PID or name."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        pid = tool_input.parameters.get("pid")
        name = tool_input.parameters.get("name")
        if pid is None and not name:
            return self._failure("Provide 'pid' or 'name'")

        try:
            import psutil

            killed = []
            if pid is not None:
                proc = psutil.Process(int(pid))
                proc.terminate()
                killed.append({"pid": proc.pid, "name": proc.name()})
            else:
                for proc in psutil.process_iter(attrs=["pid", "name"]):
                    if proc.info.get("name") == name:
                        proc.terminate()
                        killed.append({"pid": proc.pid, "name": proc.name()})

            if not killed:
                return self._failure("No matching processes found")
            logger.info("os.process_kill", count=len(killed))
            return self._success(
                f"Terminated {len(killed)} processes",
                data={"killed": killed},
            )
        except ImportError:
            return self._failure("psutil is required for process termination")
        except Exception as exc:
            return self._failure(str(exc))


class OsLaunchApplication(BaseTool):
    name = "os_launch_application"
    description = "Launch an application or open a file path."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        target = tool_input.parameters.get("target")
        args = tool_input.parameters.get("args", [])
        if not target:
            return self._failure("No target provided")

        try:
            path = _resolve_sandboxed(target)
            if platform.system() == "Windows":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
            logger.info("os.launch", target=str(path))
            return self._success(f"Launched {path.name}")
        except PermissionError:
            # If not a sandbox path, try launching as a command.
            try:
                if platform.system() == "Windows":
                    subprocess.Popen([target, *args], shell=True)
                else:
                    subprocess.Popen([target, *args])
                logger.info("os.launch", target=target)
                return self._success(f"Launched {target}")
            except Exception as exc:
                return self._failure(str(exc))
        except Exception as exc:
            return self._failure(str(exc))


class OsClipboardRead(BaseTool):
    name = "os_clipboard_read"
    description = "Read text from the system clipboard."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            text = pyperclip.paste() or ""
            return self._success("Clipboard text read", data={"text": text})
        except Exception as exc:
            return self._failure(str(exc))


class OsClipboardWrite(BaseTool):
    name = "os_clipboard_write"
    description = "Write text to the system clipboard."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        text = tool_input.parameters.get("text", "")
        try:
            pyperclip.copy(text)
            return self._success("Clipboard text updated", data={"length": len(text)})
        except Exception as exc:
            return self._failure(str(exc))
