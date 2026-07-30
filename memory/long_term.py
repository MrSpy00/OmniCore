"""Long-term memory backed by ChromaDB for semantic recall.

Embeds messages and documents into a vector store so the Cognitive Router
can query past interactions and user preferences by meaning rather than
exact keyword match.
"""

from __future__ import annotations

import hashlib
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from config.logging import get_logger
from config.settings import get_settings

logger = get_logger(__name__)

_COLLECTION_NAME = "omnicore_memory"


class LongTermMemory:
    """ChromaDB-backed semantic memory.

    Parameters
    ----------
    persist_dir:
        Override the persistence directory from settings.
    """

    def __init__(self, persist_dir: str | None = None) -> None:
        settings = get_settings()
        self._persist_dir = persist_dir or str(settings.chroma_persist_dir)
        self._client = chromadb.PersistentClient(
            path=self._persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "long_term.initialized",
            persist_dir=self._persist_dir,
            doc_count=self._collection.count(),
        )

    # -- write ----------------------------------------------------------------

    def store(
        self,
        text: str,
        *,
        doc_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Embed and store a piece of text. Returns the document ID."""
        doc_id = doc_id or hashlib.sha256(text.encode()).hexdigest()[:16]
        self._collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata or {}],
        )
        logger.debug("long_term.stored", doc_id=doc_id)
        return doc_id

    # -- read -----------------------------------------------------------------

    def recall(
        self,
        query: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the top-*n_results* documents semantically close to *query*.

        Returns a list of dicts with keys: ``id``, ``document``, ``metadata``,
        ``distance``.
        """
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results, self._collection.count() or 1),
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)
        ids: list[list[str]] = results.get("ids") or [[]]  # type: ignore[assignment]
        documents: list[list[str]] = results.get("documents") or [[]]  # type: ignore[assignment]
        metadatas: list[list[dict]] = results.get("metadatas") or [[]]  # type: ignore[assignment]
        distances: list[list[float]] = results.get("distances") or [[]]  # type: ignore[assignment]
        items: list[dict[str, Any]] = []
        for i in range(len(ids[0])):
            items.append(
                {
                    "id": ids[0][i],
                    "document": documents[0][i] if documents[0] else "",
                    "metadata": metadatas[0][i] if metadatas[0] else {},
                    "distance": distances[0][i] if distances[0] else None,
                }
            )
        logger.debug("long_term.recall", query=query[:80], n_results=len(items))
        return items

    def get_all_memories_categorized(self) -> dict[str, list[str]]:
        """Return all memories grouped by category (identity, preferences, projects, etc.)."""
        if self._collection.count() == 0:
            return {}

        results = self._collection.get(include=["documents", "metadatas"])
        documents: list[str] = results.get("documents") or []
        metadatas: list[dict] = results.get("metadatas") or []

        categories: dict[str, list[str]] = {
            "identity": [],
            "preferences": [],
            "projects": [],
            "relationships": [],
            "wishes": [],
            "notes": [],
        }

        for doc, meta in zip(documents, metadatas):
            cat = (meta.get("category") or "notes").lower()
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(doc)

        return {k: v for k, v in categories.items() if v}

    def format_memory_for_prompt(self) -> str:
        """Format stored memories as a clean block for system prompt injection."""
        cat_memories = self.get_all_memories_categorized()
        if not cat_memories:
            return ""

        lines = ["--- KALICI HAFIZA / PERSISTENT MEMORY ---"]
        cat_titles = {
            "identity": "👤 Kimlik & Kişisel Bilgiler / Identity",
            "preferences": "⭐ Tercihler & Zevkler / Preferences",
            "projects": "🚀 Projeler & Çalışmalar / Projects",
            "relationships": "👥 İlişkiler / Relationships",
            "wishes": "🎯 İstekler & Hedefler / Wishes & Goals",
            "notes": "📝 Genel Notlar / General Notes",
        }
        for cat, items in cat_memories.items():
            title = cat_titles.get(cat, f"📌 {cat.capitalize()}")
            lines.append(f"{title}:")
            for item in items:
                lines.append(f"  - {item}")
        lines.append("------------------------------------------")
        return "\n".join(lines)

    # -- admin ----------------------------------------------------------------

    def count(self) -> int:
        """Return total number of stored documents."""
        return self._collection.count()

    def delete(self, doc_id: str) -> None:
        """Delete a single document by ID."""
        self._collection.delete(ids=[doc_id])
        logger.info("long_term.deleted", doc_id=doc_id)

    def reset(self) -> None:
        """Drop and recreate the collection. Destructive."""
        self._client.delete_collection(_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("long_term.reset")
