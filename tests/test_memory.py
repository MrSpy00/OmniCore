"""Tests for memory subsystems."""

from __future__ import annotations

import pytest

from memory.short_term import ShortTermMemory
from models.messages import Message, MessageRole


class TestShortTermMemory:
    def test_add_and_retrieve_messages(self):
        stm = ShortTermMemory(max_messages=5)
        msg = Message(role=MessageRole.USER, content="Hello")
        stm.add_message("conv1", msg)

        recent = stm.get_recent_messages("conv1")
        assert len(recent) == 1
        assert recent[0].content == "Hello"

    def test_eviction_when_max_exceeded(self):
        stm = ShortTermMemory(max_messages=3)
        for i in range(5):
            stm.add_message("conv1", Message(role=MessageRole.USER, content=f"msg-{i}"))

        recent = stm.get_recent_messages("conv1")
        assert len(recent) == 3
        # Oldest messages should be evicted.
        assert recent[0].content == "msg-2"
        assert recent[2].content == "msg-4"

    def test_clear_removes_conversation(self):
        stm = ShortTermMemory()
        stm.add_message("conv1", Message(role=MessageRole.USER, content="hi"))
        stm.clear("conv1")
        assert stm.get_recent_messages("conv1") == []

    def test_get_conversation_returns_empty_for_unknown(self):
        stm = ShortTermMemory()
        conv = stm.get_conversation("nonexistent")
        assert conv.messages == []

    def test_compressed_snapshots_created_after_eviction(self):
        stm = ShortTermMemory(max_messages=2)
        stm.add_message("conv1", Message(role=MessageRole.USER, content="first"))
        stm.add_message("conv1", Message(role=MessageRole.ASSISTANT, content="second"))
        stm.add_message("conv1", Message(role=MessageRole.USER, content="third"))

        snapshots = stm.get_compressed_snapshots("conv1")
        assert len(snapshots) == 1
        assert "first" in snapshots[0]


class TestStateTracker:
    @pytest.mark.asyncio
    async def test_save_and_get_task(self, state_tracker):
        await state_tracker.save_task("t1", "do something", "executing")
        task = await state_tracker.get_task("t1")
        assert task is not None
        assert task["user_request"] == "do something"
        assert task["status"] == "executing"

    @pytest.mark.asyncio
    async def test_audit_log(self, state_tracker):
        await state_tracker.log_audit("test_event", "some detail", user_id="u1")
        logs = await state_tracker.get_audit_log(limit=10)
        assert len(logs) == 1
        assert logs[0]["event_type"] == "test_event"

    @pytest.mark.asyncio
    async def test_list_tasks_by_status(self, state_tracker):
        await state_tracker.save_task("t1", "task one", "completed")
        await state_tracker.save_task("t2", "task two", "executing")
        completed = await state_tracker.list_tasks(status="completed")
        assert len(completed) == 1
        assert completed[0]["id"] == "t1"


class TestSemanticEmbedding:
    """Test embedding generator and fallback vector behavior."""

    def test_semantic_embedding_generation(self):
        from memory.long_term import SemanticEmbedding

        embedder = SemanticEmbedding()
        assert embedder.name() == "semantic_embedding"

        docs = ["Hello world", "OmniCore assistant"]
        vectors = embedder(docs)
        assert len(vectors) == 2
        assert len(vectors[0]) == 384
        assert len(vectors[1]) == 384

        # Verify unit norm
        norm = sum(x * x for x in vectors[0]) ** 0.5
        assert abs(norm - 1.0) < 1e-3

    def test_embed_query(self):
        from memory.long_term import SemanticEmbedding

        embedder = SemanticEmbedding()
        q_vec = embedder.embed_query(["search query"])
        assert len(q_vec) == 1
        assert len(q_vec[0]) == 384


class TestLongTermMemory:
    """Test LongTermMemory storage, recall, and lifecycle."""

    @pytest.fixture()
    def ltm(self, tmp_path):
        from memory.long_term import LongTermMemory

        chroma_dir = str(tmp_path / "chroma_test")
        memory = LongTermMemory(persist_dir=chroma_dir)
        yield memory
        memory.reset()

    def test_store_and_recall_flow(self, ltm):
        doc_id = ltm.store("Python async programming", metadata={"category": "notes"})
        assert doc_id is not None
        assert ltm.count() >= 1

        results = ltm.recall("async programming", n_results=5)
        assert len(results) >= 1
        assert "async" in results[0]["document"].lower()

    def test_recall_empty_query(self, ltm):
        ltm.store("Some data")
        assert ltm.recall("") == []
        assert ltm.recall("   ") == []

    def test_delete_and_clear(self, ltm):
        doc_id = ltm.store("Temporary secret", doc_id="sec-1")
        assert ltm.count() >= 1
        ltm.delete(doc_id)
        assert ltm.count() == 0

    def test_categorized_memories_and_format(self, ltm):
        ltm.store("User prefers dark mode", metadata={"category": "preferences"})
        ltm.store("OmniCore release v1.0", metadata={"category": "projects"})

        categorized = ltm.get_all_memories_categorized()
        assert "preferences" in categorized
        assert "projects" in categorized

        formatted = ltm.format_memory_for_prompt()
        assert "Preferences" in formatted
        assert "Projects" in formatted
