"""Initialize the SQLite database with the canonical schema.

Usage::

    uv run python scripts/setup_db.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from config.settings import get_settings
from memory.state import StateTracker


async def _setup() -> None:
    settings = get_settings()
    db_path = settings.sqlite_db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    tracker = StateTracker(db_path)
    await tracker.initialize()
    await tracker.close()
    print(f"Database initialized at {db_path}")


if __name__ == "__main__":
    asyncio.run(_setup())
