"""Developer Toolkit — safe code execution and DB inspection."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

import aiosqlite

from config.settings import get_settings
from memory.state import StateTracker
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


class DevTodoTracker(BaseTool):
    name = "dev_todo_tracker"
    description = (
        "Manage plan todos in OmniCore SQLite state. "
        "Actions: upsert, set_status, add_dependency, list, ready."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(params.get("action", "list")).strip().lower()

        settings = get_settings()
        tracker = StateTracker(settings.sqlite_db_path)
        await tracker.initialize()
        try:
            handlers = {
                "upsert": self._action_upsert,
                "set_status": self._action_set_status,
                "add_dependency": self._action_add_dependency,
                "list": self._action_list,
                "ready": self._action_ready,
            }
            handler = handlers.get(action)
            if handler is None:
                return self._failure(
                    "Unsupported action. Use one of: upsert, set_status, "
                    "add_dependency, list, ready"
                )
            return await handler(tracker, params)
        except Exception as exc:
            return self._failure(f"{type(exc).__name__}: {exc}")
        finally:
            await tracker.close()

    async def _action_upsert(self, tracker: StateTracker, params: dict) -> ToolOutput:
        todo_id = str(params.get("id", "")).strip()
        title = str(params.get("title", "")).strip()
        description = str(params.get("description", "")).strip()
        status = str(params.get("status", "pending")).strip().lower()
        if not todo_id or not title:
            return self._failure("id and title are required for upsert")
        await tracker.upsert_todo(todo_id, title, description=description, status=status)
        return self._success("Todo upserted", data={"id": todo_id, "status": status})

    async def _action_set_status(self, tracker: StateTracker, params: dict) -> ToolOutput:
        todo_id = str(params.get("id", "")).strip()
        status = str(params.get("status", "")).strip().lower()
        if not todo_id or not status:
            return self._failure("id and status are required for set_status")
        await tracker.set_todo_status(todo_id, status)
        return self._success("Todo status updated", data={"id": todo_id, "status": status})

    async def _action_add_dependency(self, tracker: StateTracker, params: dict) -> ToolOutput:
        todo_id = str(params.get("id", "")).strip()
        depends_on = str(params.get("depends_on", "")).strip()
        if not todo_id or not depends_on:
            return self._failure("id and depends_on are required for add_dependency")
        await tracker.add_todo_dependency(todo_id, depends_on)
        return self._success(
            "Todo dependency added",
            data={"id": todo_id, "depends_on": depends_on},
        )

    async def _action_list(self, tracker: StateTracker, params: dict) -> ToolOutput:
        status = params.get("status")
        limit = int(params.get("limit", 100))
        rows = await tracker.list_todos(str(status) if status else None, limit=limit)
        return self._success(
            f"Listed {len(rows)} todos",
            data={"todos": rows},
        )

    async def _action_ready(self, tracker: StateTracker, params: dict) -> ToolOutput:
        limit = int(params.get("limit", 100))
        rows = await tracker.list_ready_todos(limit=limit)
        return self._success(
            f"Listed {len(rows)} ready todos",
            data={"todos": rows},
        )
