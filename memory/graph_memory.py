"""Knowledge Graph Memory Engine — SQLite-backed entity-relation store.

Enables OmniCore to store and traverse directional relations between entities
(e.g., User -> owns -> OmniCore, OmniCore -> uses -> ChromaDB) for multi-hop
contextual recall.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from config.logging import get_logger
from config.settings import get_settings

logger = get_logger(__name__)


class GraphMemory:
    """SQLite-backed Knowledge Graph Store."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self._db_path = str(db_path or settings.sqlite_db_path)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Initialize database connection and schema."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_entities (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS graph_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(subject, predicate, object)
            );
            """
        )
        await self._db.commit()
        logger.info("graph_memory.initialized", db_path=self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def add_relation(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
    ) -> int:
        """Insert or ignore a directional relation between subject and object."""
        if not self._db:
            await self.initialize()
        assert self._db
        async with self._db.execute(
            """
            INSERT OR IGNORE INTO graph_relations (subject, predicate, object, confidence)
            VALUES (?, ?, ?, ?)
            """,
            (subject.strip(), predicate.strip(), obj.strip(), confidence),
        ) as cursor:
            await self._db.commit()
            return cursor.lastrowid or 0

    async def query_relations(self, entity_name: str) -> list[dict[str, Any]]:
        """Retrieve all relations where entity_name is either subject or object."""
        if not self._db:
            await self.initialize()
        assert self._db
        async with self._db.execute(
            """
            SELECT subject, predicate, object, confidence FROM graph_relations
            WHERE LOWER(subject) = LOWER(?) OR LOWER(object) = LOWER(?)
            """,
            (entity_name.strip(), entity_name.strip()),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "subject": r[0],
                    "predicate": r[1],
                    "object": r[2],
                    "confidence": r[3],
                }
                for r in rows
            ]

    async def format_graph_for_prompt(self, query: str) -> str:
        """Format matching entity graph relations as a clean block for system prompt."""
        if not self._db:
            return ""

        words = [w for w in query.split() if len(w) > 3]
        all_relations: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for word in words[:4]:
            rels = await self.query_relations(word)
            for r in rels:
                key = (r["subject"], r["predicate"], r["object"])
                if key not in seen:
                    seen.add(key)
                    all_relations.append(r)

        if not all_relations:
            return ""

        lines = ["--- KNOWLEDGE GRAPH RELATIONS ---"]
        for r in all_relations[:10]:
            lines.append(f"  ({r['subject']}) --[{r['predicate']}]--> ({r['object']})")
        lines.append("----------------------------------")
        return "\n".join(lines)

    async def export_graph_data(self, limit: int = 150) -> dict[str, Any]:
        """Export full graph network formatted for Cytoscape.js visualizer."""
        if not self._db:
            await self.initialize()
        assert self._db

        async with self._db.execute(
            """
            SELECT subject, predicate, object, confidence FROM graph_relations
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []

        for row in rows:
            s, p, o, conf = row[0], row[1], row[2], row[3]
            for name in (s, o):
                if name not in nodes:
                    nodes[name] = {"id": name, "label": name}

            edges.append({
                "id": f"{s}_{p}_{o}",
                "source": s,
                "target": o,
                "label": p,
                "confidence": conf,
            })

        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "count": len(edges),
        }

    async def extract_and_store_from_text(self, text: str) -> int:
        """Metinden otomatik olarak varlık-ilişki çıkarır ve grafa ekler."""
        try:
            from memory.graph_extractor import extract_entities_and_relations
            triples = extract_entities_and_relations(text)
            count = 0
            for triple in triples:
                await self.add_relation(
                    triple["subject"],
                    triple["predicate"],
                    triple["object"],
                    confidence=0.8,
                )
                count += 1
            return count
        except Exception:
            return 0

