"""Generate db/schema.sql from the canonical _SCHEMA in memory/state.py.

Usage:
    python scripts/generate_schema_sql.py
"""

from __future__ import annotations

from pathlib import Path

from memory.state import _SCHEMA

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

header = (
    "-- OmniCore SQLite Schema\n"
    "-- AUTO-GENERATED from memory/state.py — do not edit manually.\n"
    "-- Run: python scripts/generate_schema_sql.py\n\n"
)

_SCHEMA_PATH.write_text(header + _SCHEMA + "\n", encoding="utf-8")
print(f"Schema written to {_SCHEMA_PATH}")
