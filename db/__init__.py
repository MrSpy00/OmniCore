"""Database subsystem for OmniCore.

Provides unified SQLite connection management with WAL mode,
foreign key enforcement, and thread-safe access.
"""

from db.connection import SQLiteManager, get_db_path

__all__ = ["SQLiteManager", "get_db_path"]
