"""System Optimizer Toolkit — cleanup and disk analysis."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


class SysCleanTempFiles(BaseTool):
    name = "sys_clean_temp_files"
    description = "Clear Windows temp directories and report freed space."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        freed = await asyncio.to_thread(_clean_temp_files_sync)
        freed_mb = round(freed / (1024 * 1024), 2)
        return self._success("Temp files cleaned", data={"freed_mb": freed_mb})


class SysFindLargeFiles(BaseTool):
    name = "sys_find_large_files"
    description = "Find top 10 largest files over a size threshold."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        root = tool_input.parameters.get("root", ".")
        min_mb = float(tool_input.parameters.get("min_mb", 100))

        root_path = resolve_user_path(str(root))[0]
        top = await asyncio.to_thread(_find_large_files_sync, root_path, min_mb)
        return self._success("Large files scanned", data={"files": top})


class SysFlushDnsCache(BaseTool):
    name = "sys_flush_dns_cache"
    description = "Flush Windows DNS cache using ipconfig /flushdns."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["ipconfig", "/flushdns"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return self._success(
                "DNS cache flushed",
                data={"stdout": result.stdout, "stderr": result.stderr},
            )
        except Exception as exc:
            return self._failure(str(exc))


def _clean_temp_files_sync() -> int:
    temp_paths = [os.getenv("TEMP", "")]
    if os.name == "nt":
        temp_paths.append(r"C:\Windows\Temp")
    else:
        temp_paths.append("/tmp")
    freed = 0
    for temp in temp_paths:
        if not temp:
            continue
        temp_dir = Path(temp)
        if not temp_dir.exists():
            continue
        for path in temp_dir.rglob("*"):
            try:
                if path.is_file():
                    freed += path.stat().st_size
                    path.unlink()
                elif path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                continue
    return freed


def _find_large_files_sync(root_path: Path, min_mb: float) -> list[dict[str, float | str]]:
    results: list[dict[str, float | str]] = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb >= min_mb:
            results.append({"path": str(path), "size_mb": round(size_mb, 2)})

    results.sort(key=lambda x: float(x["size_mb"]), reverse=True)
    return results[:10]
