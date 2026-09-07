"""Unified SQLite Connection Manager.

Provides thread-safe, WAL-mode SQLite connections with:
- Connection pooling per database path
- Automatic WAL mode and foreign key enforcement
- Configurable busy timeout
- Thread-safe access via locks

Usage::

    from db.connection import SQLiteManager

    db = SQLiteManager.get_db(Path("./data/omnicore.db"))
    with db.execute("SELECT * FROM tasks WHERE status = ?", ("pending",)) as cursor:
        rows = cursor.fetchall()
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from config.logging import get_logger

logger = get_logger(__name__)

# Default configuration
_DEFAULT_BUSY_TIMEOUT_MS = 10000  # 10 seconds
_DEFAULT_WAL_MODE = True
_DEFAULT_FOREIGN_KEYS = True


class SQLiteManager:
    """Thread-safe SQLite connection manager with connection pooling.

    Each database path gets a single shared connection configured with
    WAL mode and foreign key enforcement.
    """

    _instances: dict[str, SQLiteManager] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        db_path: Path,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
        wal_mode: bool = _DEFAULT_WAL_MODE,
        foreign_keys: bool = _DEFAULT_FOREIGN_KEYS,
    ) -> None:
        self._db_path = db_path.resolve()
        self._busy_timeout_ms = busy_timeout_ms
        self._wal_mode = wal_mode
        self._foreign_keys = foreign_keys
        self._conn: sqlite3.Connection | None = None
        self._write_lock = threading.Lock()
        self._local = threading.local()

    @classmethod
    def get_db(
        cls,
        db_path: Path,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
        wal_mode: bool = _DEFAULT_WAL_MODE,
        foreign_keys: bool = _DEFAULT_FOREIGN_KEYS,
    ) -> SQLiteManager:
        """Get or create a SQLiteManager for the given database path.

        This is the primary entry point for obtaining a database connection.
        """
        key = str(db_path.resolve())
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(
                    db_path=db_path,
                    busy_timeout_ms=busy_timeout_ms,
                    wal_mode=wal_mode,
                    foreign_keys=foreign_keys,
                )
            return cls._instances[key]

    @classmethod
    def reset(cls) -> None:
        """Close and remove all cached database instances. Useful for testing."""
        with cls._lock:
            for instance in cls._instances.values():
                instance.close()
            cls._instances.clear()

    @property
    def path(self) -> Path:
        """Return the database file path."""
        return self._db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create the shared database connection."""
        if self._conn is None:
            # Ensure parent directory exists
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(
                str(self._db_path),
                timeout=self._busy_timeout_ms / 1000,
                check_same_thread=False,
                isolation_level=None,  # Autocommit mode for WAL
            )
            self._conn.row_factory = sqlite3.Row

            # Configure connection
            cursor = self._conn.cursor()
            try:
                if self._wal_mode:
                    cursor.execute("PRAGMA journal_mode=WAL;")
                if self._foreign_keys:
                    cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms};")
            finally:
                cursor.close()

            logger.debug("sqlite.connection_created", path=str(self._db_path))

        return self._conn

    @contextmanager
    def execute(
        self,
        query: str,
        parameters: tuple | dict | None = None,
    ) -> Iterator[sqlite3.Cursor]:
        """Execute a query and return a cursor.

        Usage::

            with db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)) as cursor:
                rows = cursor.fetchall()
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if parameters:
                cursor.execute(query, parameters)
            else:
                cursor.execute(query)
            yield cursor
        except sqlite3.Error as exc:
            logger.error("sqlite.query_error", query=query, error=str(exc))
            raise
        finally:
            cursor.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Execute multiple statements in a transaction.

        Usage::

            with db.transaction() as conn:
                conn.execute("INSERT INTO tasks ...")
                conn.execute("INSERT INTO audit_log ...")
        """
        conn = self._get_connection()
        with self._write_lock:
            try:
                conn.execute("BEGIN")
                yield conn
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error as exc:
                logger.warning("sqlite.close_error", path=str(self._db_path), error=str(exc))
            finally:
                self._conn = None


def get_db_path(default: str = "./data/omnicore.db") -> Path:
    """Get the database path from settings or use default."""
    try:
        from config.settings import get_settings

        settings = get_settings()
        if hasattr(settings, "sqlite_db_path") and settings.sqlite_db_path:
            return Path(settings.sqlite_db_path)
    except Exception:
        pass
    return Path(default)
