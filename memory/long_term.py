"""Long-term memory backed by ChromaDB for semantic recall.

Embeds messages and documents into a vector store so the Cognitive Router
can query past interactions and user preferences by meaning rather than
exact keyword match.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from chromadb.config import Settings as ChromaSettings

from config.logging import get_logger
from config.settings import get_settings

logger = get_logger(__name__)

_COLLECTION_NAME = "omnicore_memory"


class FastLightweightEmbedding(EmbeddingFunction[Documents]):
    """Deterministic, fast on-device embedding function.

    Provides 64-dimensional normalized word-hash vectors. Requires zero C++
    compilers or heavy ONNX runtimes. Never fails or raises onnxruntime errors.
    """

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        return self._embed(input)

    def embed_query(self, input: Documents) -> Embeddings:
        return self._embed(input)

    def _embed(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            vec = [0.0] * 64
            words = text.lower().split()
            for w in words:
                h = int(hashlib.md5(w.encode()).hexdigest(), 16)
                idx = h % 64
                vec[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings


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

        # Always use lightweight embedding to avoid onnxruntime dependency issues
        embedding_fn = FastLightweightEmbedding()

        try:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False, is_persistent=True),
            )
            col_kwargs: dict[str, Any] = {
                "name": _COLLECTION_NAME,
                "metadata": {"hnsw:space": "cosine"},
            }
            if embedding_fn:
                col_kwargs["embedding_function"] = embedding_fn
            self._collection = self._client.get_or_create_collection(**col_kwargs)
        except Exception as exc:
            logger.warning("long_term.persistent_failed_fallback_ephemeral", error=str(exc))
            self._client = chromadb.EphemeralClient(
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            col_kwargs = {
                "name": _COLLECTION_NAME,
                "metadata": {"hnsw:space": "cosine"},
            }
            if embedding_fn:
                col_kwargs["embedding_function"] = embedding_fn
            self._collection = self._client.get_or_create_collection(**col_kwargs)
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
        upsert_kwargs: dict[str, Any] = {
            "ids": [doc_id],
            "documents": [text],
        }
        if metadata:
            upsert_kwargs["metadatas"] = [metadata]
        try:
            self._collection.upsert(**upsert_kwargs)
            logger.debug("long_term.stored", doc_id=doc_id)
        except Exception as exc:
            logger.warning("long_term.store_fallback_lightweight", error=str(exc))
            try:
                self._collection = self._client.get_or_create_collection(
                    name=_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                )
                self._collection.upsert(**upsert_kwargs)
            except Exception as e2:
                logger.error("long_term.store_fatal", error=str(e2))
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
        try:
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": min(n_results, self._collection.count() or 1),
            }
            if where:
                kwargs["where"] = where
            results = self._collection.query(**kwargs)
        except Exception as exc:
            logger.warning("long_term.recall_fallback_lightweight", error=str(exc))
            try:
                self._collection = self._client.get_or_create_collection(
                    name=_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"},
                    embedding_function=FastLightweightEmbedding(),
                )
                results = self._collection.query(
                    query_texts=[query],
                    n_results=min(n_results, self._collection.count() or 1),
                )
            except Exception as e2:
                logger.error("long_term.recall_fatal", error=str(e2))
                return []

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

    _KNOWN_CATEGORIES = ("identity", "preferences", "projects", "relationships", "wishes", "notes")
    _MAX_PER_CATEGORY = 50

    def get_all_memories_categorized(
        self, limit_per_category: int = _MAX_PER_CATEGORY
    ) -> dict[str, list[str]]:
        """Return all memories grouped by category with per-category limits."""
        if self._collection.count() == 0:
            return {}

        categories: dict[str, list[str]] = {}

        for cat in self._KNOWN_CATEGORIES:
            try:
                results = self._collection.get(
                    where={"category": cat},
                    include=["documents"],
                    limit=limit_per_category,
                )
                docs = results.get("documents") or []
                if docs:
                    categories[cat] = docs
            except Exception:
                continue

        uncategorized_results = self._collection.get(
            include=["documents", "metadatas"],
            limit=limit_per_category,
        )
        docs = uncategorized_results.get("documents") or []
        metas = uncategorized_results.get("metadatas") or []
        extra: list[str] = []
        for doc, meta in zip(docs, metas):
            cat = (meta.get("category") or "").lower()
            if cat not in self._KNOWN_CATEGORIES:
                extra.append(doc)
        if extra:
            categories["notes"] = categories.get("notes", []) + extra

        return categories

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
