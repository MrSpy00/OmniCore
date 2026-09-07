"""Database Explorer Toolkit — Schema introspection and safe query execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class DbInspectSchema(BaseTool):
    """Introspect SQLite database schema, tables, columns, and data types."""

    name = "db_inspect_schema"
    description = (
        "Introspect SQLite database tables, column names, data types, and primary keys. "
        "Parameters: db_path (path to SQLite database file)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path_str = str(self._first_param(params, "db_path", "path", default="") or "").strip()

        if not path_str:
            return self._failure("db_path parameter is required.")

        target = Path(path_str)
        if not target.exists():
            return self._failure(f"Database file not found: {target}")

        try:
            schema_data = await _introspect_sqlite_schema(target)
            return self._success(
                f"Schema introspection for {target.name} complete.",
                data={"db_path": str(target), "tables": schema_data},
            )
        except Exception as exc:
            return self._failure(f"Failed to inspect schema: {exc}")


class DbQueryExecute(BaseTool):
    """Execute a SQL query against a target SQLite database."""

    name = "db_query_execute"
    description = (
        "Execute a SQL query against a SQLite database. "
        "Parameters: db_path (path to SQLite database file), query (SQL string)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path_str = str(self._first_param(params, "db_path", "path", default="") or "").strip()
        query = str(self._first_param(params, "query", "sql", default="") or "").strip()

        if not path_str or not query:
            return self._failure("db_path and query parameters are required.")

        target = Path(path_str)
        if not target.parent.exists():
            return self._failure(f"Database parent directory not found: {target.parent}")

        try:
            rows, columns = await _execute_sql_query(target, query)
            return self._success(
                f"SQL query executed successfully. Returned {len(rows)} rows.",
                data={"columns": columns, "rows": rows, "row_count": len(rows)},
            )
        except Exception as exc:
            return self._failure(f"Failed to execute SQL query: {exc}")


async def _introspect_sqlite_schema(db_path: Path) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table';") as cursor:
            table_rows = await cursor.fetchall()
            table_names = [r[0] for r in table_rows]

        for table in table_names:
            async with db.execute(f"PRAGMA table_info({table});") as col_cursor:
                cols = await col_cursor.fetchall()
                tables[table] = [
                    {
                        "cid": col[0],
                        "name": col[1],
                        "type": col[2],
                        "notnull": col[3],
                        "pk": col[5],
                    }
                    for col in cols
                ]
    return tables


async def _execute_sql_query(db_path: Path, query: str) -> tuple[list[list[Any]], list[str]]:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(query) as cursor:
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = await cursor.fetchall()
                return [list(r) for r in rows], columns
            await db.commit()
            return [], []
