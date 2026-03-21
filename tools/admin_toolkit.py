"""Admin Toolkit — advanced power-user operations."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class AdminExportRegistryKey(BaseTool):
    name = "admin_export_registry_key"
    description = "Export a Windows registry key to a .reg file."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        key_path = tool_input.parameters.get("key_path", "")
        output_path = tool_input.parameters.get("output_path", "registry_export.reg")
        if not key_path:
            return self._failure("key_path is required")

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["reg", "export", key_path, output_path, "/y"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return self._success(
                "Registry export completed",
                data={"stdout": result.stdout, "stderr": result.stderr},
            )
        except Exception as exc:
            return self._failure(str(exc))


class AdminListStartupPrograms(BaseTool):
    name = "admin_list_startup_programs"
    description = "List Windows startup programs from the registry."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["reg", "query", "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return self._success(
                "Startup programs listed",
                data={"output": result.stdout},
            )
        except Exception as exc:
            return self._failure(str(exc))


class AdminGenerateDiskReport(BaseTool):
    name = "admin_generate_disk_report"
    description = "Generate a simple disk usage report for a directory."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        root = tool_input.parameters.get("root", ".")
        path = Path(root).expanduser().resolve()
        sizes = []
        try:
            sizes = await asyncio.to_thread(_disk_report, path)

            sizes.sort(key=lambda x: x["size_mb"], reverse=True)
            return self._success("Disk report generated", data={"entries": sizes})
        except Exception as exc:
            return self._failure(str(exc))


class AdminNetworkSnapshot(BaseTool):
    name = "admin_network_snapshot"
    description = "Capture current network connections and listening ports."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return self._success(
                "Network snapshot captured",
                data={"output": result.stdout},
            )
        except Exception as exc:
            return self._failure(str(exc))


class AdminSummarizeEventLogs(BaseTool):
    name = "admin_summarize_event_logs"
    description = "Export recent Windows event logs (Application)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "wevtutil",
                    "qe",
                    "Application",
                    "/c:50",
                    "/f:text",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return self._success(
                "Event logs exported",
                data={"output": result.stdout},
            )
        except Exception as exc:
            return self._failure(str(exc))


def _disk_report(path: Path) -> list[dict[str, float | str]]:
    sizes: list[dict[str, float | str]] = []
    for child in path.iterdir():
        if child.is_dir():
            total = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
            sizes.append({"path": str(child), "size_mb": round(total / (1024 * 1024), 2)})
        elif child.is_file():
            sizes.append(
                {
                    "path": str(child),
                    "size_mb": round(child.stat().st_size / (1024 * 1024), 2),
                }
            )
    sizes.sort(key=lambda x: float(x["size_mb"]), reverse=True)
    return sizes
