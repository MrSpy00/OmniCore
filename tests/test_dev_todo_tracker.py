"""Tests for developer todo tracker tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from _pytest.monkeypatch import MonkeyPatch

from models.tools import ToolInput, ToolStatus
from tools.developer_toolkit import DevTodoTracker


@pytest.mark.asyncio
async def test_todo_tracker_upsert_and_list(tmp_path: Path, monkeypatch: MonkeyPatch):
    db_path: Path = tmp_path / "todo_state.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    from config.settings import get_settings

    get_settings.cache_clear()

    tool = DevTodoTracker()
    upsert_result = await tool.execute(
        ToolInput(
            tool_name="dev_todo_tracker",
            parameters={"action": "upsert", "id": "todo-1", "title": "First todo"},
        )
    )
    assert upsert_result.status == ToolStatus.SUCCESS

    list_result = await tool.execute(
        ToolInput(
            tool_name="dev_todo_tracker",
            parameters={"action": "list"},
        )
    )
    assert list_result.status == ToolStatus.SUCCESS
    list_result_any: Any = list_result
    todos = cast(list[dict[str, Any]], list_result_any.data.get("todos", []))
    assert any(t.get("id") == "todo-1" for t in todos)


@pytest.mark.asyncio
async def test_todo_tracker_ready_respects_dependencies(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
):
    db_path: Path = tmp_path / "todo_state.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))

    from config.settings import get_settings

    get_settings.cache_clear()

    tool = DevTodoTracker()

    await tool.execute(
        ToolInput(
            tool_name="dev_todo_tracker",
            parameters={"action": "upsert", "id": "a", "title": "Todo A"},
        )
    )
    await tool.execute(
        ToolInput(
            tool_name="dev_todo_tracker",
            parameters={"action": "upsert", "id": "b", "title": "Todo B"},
        )
    )
    await tool.execute(
        ToolInput(
            tool_name="dev_todo_tracker",
            parameters={"action": "add_dependency", "id": "b", "depends_on": "a"},
        )
    )

    ready_before = await tool.execute(
        ToolInput(tool_name="dev_todo_tracker", parameters={"action": "ready"})
    )
    ready_before_any: Any = ready_before
    todos_before = cast(list[dict[str, Any]], ready_before_any.data.get("todos", []))
    ready_ids_before = {str(t.get("id")) for t in todos_before}
    assert "a" in ready_ids_before
    assert "b" not in ready_ids_before

    status_result = await tool.execute(
        ToolInput(
            tool_name="dev_todo_tracker",
            parameters={"action": "set_status", "id": "a", "status": "done"},
        )
    )
    assert status_result.status == ToolStatus.SUCCESS

    ready_after = await tool.execute(
        ToolInput(tool_name="dev_todo_tracker", parameters={"action": "ready"})
    )
    ready_after_any: Any = ready_after
    todos_after = cast(list[dict[str, Any]], ready_after_any.data.get("todos", []))
    ready_ids_after = {str(t.get("id")) for t in todos_after}
    assert "b" in ready_ids_after
