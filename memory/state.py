"""SQLite-backed state tracker for tasks, cron jobs, and audit log.

Uses aiosqlite for non-blocking access from the async Telegram gateway
and scheduler.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from config.logging import get_logger
from config.settings import get_settings

logger = get_logger(__name__)


class StateTracker:
    """Async SQLite state persistence.

    Typical lifecycle::

        tracker = StateTracker()
        await tracker.initialize()   # creates tables if needed
        ...
        await tracker.close()
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self._db_path = str(db_path or settings.sqlite_db_path)
        self._db: aiosqlite.Connection | None = None

    # -- lifecycle ------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database and ensure schema exists."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._create_tables()
        logger.info("state_tracker.initialized", db_path=self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # -- tasks ----------------------------------------------------------------

    async def save_task(
        self,
        task_id: str,
        user_request: str,
        status: str,
        plan_json: str = "",
    ) -> None:
        """Insert or update a task record."""
        assert self._db
        await self._db.execute(
            """
            INSERT INTO tasks (id, user_request, status, plan_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                plan_json = excluded.plan_json,
                updated_at = excluded.updated_at
            """,
            (task_id, user_request, status, plan_json, _now_iso()),
        )
        await self._db.commit()

    async def get_task(self, task_id: str) -> dict | None:
        """Fetch a task by ID."""
        assert self._db
        async with self._db.execute(
            "SELECT id, user_request, status, plan_json, created_at, updated_at "
            "FROM tasks WHERE id = ?",
            (task_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "user_request": row[1],
                "status": row[2],
                "plan_json": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }

    async def list_tasks(self, status: str | None = None, limit: int = 50) -> list[dict]:
        """List tasks, optionally filtered by status."""
        assert self._db
        if status:
            query = (
                "SELECT id, user_request, status, created_at, updated_at "
                "FROM tasks WHERE status = ? ORDER BY updated_at DESC LIMIT ?"
            )
            params: tuple = (status, limit)
        else:
            query = (
                "SELECT id, user_request, status, created_at, updated_at "
                "FROM tasks ORDER BY updated_at DESC LIMIT ?"
            )
            params = (limit,)
        async with self._db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "user_request": r[1],
                    "status": r[2],
                    "created_at": r[3],
                    "updated_at": r[4],
                }
                for r in rows
            ]

    # -- audit log ------------------------------------------------------------

    async def log_audit(
        self,
        event_type: str,
        detail: str,
        user_id: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Append an entry to the audit log."""
        assert self._db
        await self._db.execute(
            "INSERT INTO audit_log (event_type, detail, user_id, metadata_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_type, detail, user_id, json.dumps(metadata or {}), _now_iso()),
        )
        await self._db.commit()

    async def get_audit_log(self, limit: int = 100) -> list[dict]:
        """Retrieve recent audit entries."""
        assert self._db
        async with self._db.execute(
            "SELECT id, event_type, detail, user_id, metadata_json, created_at "
            "FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "event_type": r[1],
                    "detail": r[2],
                    "user_id": r[3],
                    "metadata": json.loads(r[4]),
                    "created_at": r[5],
                }
                for r in rows
            ]

    # -- scheduled jobs -------------------------------------------------------

    async def save_scheduled_job(
        self,
        job_id: str,
        job_name: str,
        cron_expr: str,
        enabled: bool = True,
        config_json: str = "{}",
    ) -> None:
        """Insert or update a scheduled job definition."""
        assert self._db
        await self._db.execute(
            """
            INSERT INTO scheduled_jobs (id, job_name, cron_expr, enabled, config_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                job_name = excluded.job_name,
                cron_expr = excluded.cron_expr,
                enabled = excluded.enabled,
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (job_id, job_name, cron_expr, enabled, config_json, _now_iso()),
        )
        await self._db.commit()

    async def list_scheduled_jobs(self, enabled_only: bool = True) -> list[dict]:
        """List scheduled jobs."""
        assert self._db
        query = (
            "SELECT id, job_name, cron_expr, enabled, config_json, updated_at FROM scheduled_jobs"
        )
        if enabled_only:
            query += " WHERE enabled = 1"
        async with self._db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": r[0],
                    "job_name": r[1],
                    "cron_expr": r[2],
                    "enabled": bool(r[3]),
                    "config": json.loads(r[4]),
                    "updated_at": r[5],
                }
                for r in rows
            ]

    # -- internal -------------------------------------------------------------

    async def _create_tables(self) -> None:
        """Create tables if they don't already exist."""
        assert self._db
        await self._db.executescript(_SCHEMA)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    user_request TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'planning',
    plan_json   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '',
    user_id       TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id          TEXT PRIMARY KEY,
    job_name    TEXT NOT NULL,
    cron_expr   TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_enabled ON scheduled_jobs(enabled);
"""
