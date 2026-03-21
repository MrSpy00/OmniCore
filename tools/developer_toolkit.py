"""Developer Toolkit — safe code execution and DB inspection."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

import aiosqlite

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class DevExecutePythonCode(BaseTool):
    name = "dev_execute_python_code"
    description = "Execute Python code in a temporary file (10s timeout)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        code = tool_input.parameters.get("code", "")
        if not code:
            return self._failure("code is required")

        timeout = int(tool_input.parameters.get("timeout", 10))

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                path = Path(tmp_dir) / "snippet.py"
                await asyncio.to_thread(path.write_text, code, encoding="utf-8")
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, str(path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            return self._success(
                "Execution completed",
                data={
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        except subprocess.TimeoutExpired:
            return self._failure(f"Execution timed out after {timeout}s")
        except Exception as exc:
            return self._failure(str(exc))


class DevRunSqliteQuery(BaseTool):
    name = "dev_run_sqlite_query"
    description = "Run a read-only SQL query against the OmniCore database."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        query = tool_input.parameters.get("query", "")
        if not query:
            return self._failure("query is required")

        if not query.strip().lower().startswith("select"):
            return self._failure("Only SELECT queries are allowed")

        try:
            settings = get_settings()
            async with aiosqlite.connect(settings.sqlite_db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query)
                rows = await cursor.fetchall()
            data = [dict(row) for row in rows]
            return self._success("Query executed", data={"rows": data})
        except Exception as exc:
            return self._failure(str(exc))
