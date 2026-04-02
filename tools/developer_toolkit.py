"""Developer Toolkit — safe code execution and DB inspection."""

from __future__ import annotations

import asyncio
import fnmatch
import glob as globlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import aiosqlite

from config.settings import get_settings
from memory.state import StateTracker
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


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


class DevGlobSearch(BaseTool):
    name = "dev_glob_search"
    description = "Find files by glob pattern with optional limit."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        pattern = str(self._first_param(params, "pattern", "glob", default="**/*")).strip()
        root_raw = str(self._first_param(params, "path", "root", default=".")).strip()
        limit = int(self._first_param(params, "limit", "max_results", default=200) or 200)
        if not pattern:
            return self._failure("pattern is required")

        root, _ = resolve_user_path(root_raw)
        if not root.exists() or not root.is_dir():
            return self._failure(f"Path not found or not directory: {root}")

        def _scan() -> list[str]:
            recursive = "**" in pattern
            full_pattern = str(root / pattern)
            matches = globlib.glob(full_pattern, recursive=recursive)
            files: list[str] = []
            for item in matches:
                p = Path(item)
                if p.is_file():
                    files.append(str(p))
                if len(files) >= limit:
                    break
            return files

        try:
            files = await asyncio.to_thread(_scan)
            return self._success(
                f"Found {len(files)} files",
                data={
                    "pattern": pattern,
                    "path": str(root),
                    "count": len(files),
                    "files": files,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class DevGrepAnalyzer(BaseTool):
    name = "dev_grep_analyzer"
    description = "Search file contents by regex with include filter and limits."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        pattern = str(self._first_param(params, "pattern", "regex", default="")).strip()
        root_raw = str(self._first_param(params, "path", "root", default=".")).strip()
        include = str(self._first_param(params, "include", default="*")).strip() or "*"
        max_files = int(self._first_param(params, "max_files", default=200) or 200)
        max_matches = int(self._first_param(params, "max_matches", default=300) or 300)

        if not pattern:
            return self._failure("pattern is required")

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return self._failure(f"Invalid regex: {exc}")

        root, _ = resolve_user_path(root_raw)
        if not root.exists() or not root.is_dir():
            return self._failure(f"Path not found or not directory: {root}")

        include_patterns = [p.strip() for p in include.split(",") if p.strip()]
        if not include_patterns:
            include_patterns = ["*"]

        def _matches_include(rel_posix: str) -> bool:
            return any(fnmatch.fnmatch(rel_posix, pat) for pat in include_patterns)

        def _scan() -> tuple[list[dict], int]:
            matches: list[dict] = []
            scanned_files = 0

            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue

                rel_posix = file_path.relative_to(root).as_posix()
                if not _matches_include(rel_posix):
                    continue

                scanned_files += 1
                if scanned_files > max_files:
                    break

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for lineno, line in enumerate(content.splitlines(), start=1):
                    if regex.search(line):
                        matches.append(
                            {
                                "file": str(file_path),
                                "line": lineno,
                                "text": line[:500],
                            }
                        )
                        if len(matches) >= max_matches:
                            return matches, scanned_files

            return matches, scanned_files

        try:
            matches, scanned_files = await asyncio.to_thread(_scan)
            return self._success(
                f"Found {len(matches)} matches",
                data={
                    "pattern": pattern,
                    "path": str(root),
                    "include": include_patterns,
                    "scanned_files": scanned_files,
                    "match_count": len(matches),
                    "matches": matches,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class AgentSpawnSubtask(BaseTool):
    name = "agent_spawn_subtask"
    description = "Generate structured delegated subtasks for swarm execution."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        objective = str(
            self._first_param(params, "objective", "goal", "description", "query", default="")
        ).strip()
        max_subtasks = int(self._first_param(params, "max_subtasks", default=4) or 4)
        max_subtasks = max(1, min(10, max_subtasks))

        if not objective:
            return self._failure("objective is required")

        raw_chunks = re.split(r"[;\n]+|\s+and\s+|\s+ve\s+", objective, flags=re.IGNORECASE)
        chunks = [c.strip(" .") for c in raw_chunks if c.strip(" .")]
        if not chunks:
            chunks = [objective]

        subtasks: list[dict] = []
        for idx, chunk in enumerate(chunks[:max_subtasks], start=1):
            lowered = chunk.lower()
            if "find" in lowered or "search" in lowered or "bul" in lowered or "ara" in lowered:
                tool_name = "dev_glob_search"
                parameters = {"pattern": "**/*", "limit": 100}
            elif "grep" in lowered or "regex" in lowered or "match" in lowered:
                tool_name = "dev_grep_analyzer"
                parameters = {"pattern": ".*", "include": "*", "max_matches": 100}
            else:
                tool_name = "dev_grep_analyzer"
                parameters = {"pattern": re.escape(chunk), "include": "*", "max_matches": 50}

            subtasks.append(
                {
                    "id": f"subtask_{idx}",
                    "description": chunk,
                    "tool_name": tool_name,
                    "parameters": parameters,
                    "is_destructive": False,
                }
            )

        return self._success(
            f"Spawned {len(subtasks)} subtasks",
            data={
                "objective": objective,
                "subtask_count": len(subtasks),
                "subtasks": subtasks,
            },
        )
