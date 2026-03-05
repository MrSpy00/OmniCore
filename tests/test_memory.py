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
