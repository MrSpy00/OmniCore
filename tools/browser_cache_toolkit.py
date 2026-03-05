"""Browser Cache Toolkit — clear common browser caches."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class SysClearBrowserCaches(BaseTool):
    name = "sys_clear_browser_caches"
    description = "Clear common browser cache folders (Chrome/Edge)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        user_home = Path.home()
        targets = [
            user_home
            / "AppData"
            / "Local"
            / "Google"
            / "Chrome"
            / "User Data"
            / "Default"
            / "Cache",
            user_home
            / "AppData"
            / "Local"
            / "Microsoft"
            / "Edge"
            / "User Data"
            / "Default"
            / "Cache",
        ]

        cleared = 0
        for target in targets:
            if not target.exists():
                continue
            try:
                cleared += sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
                await asyncio.to_thread(shutil.rmtree, target, ignore_errors=True)
            except Exception:
                continue

        return self._success("Browser caches cleared", data={"freed_bytes": cleared})
