"""Tests for OmniCore v0.38.0 agentic OS features."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.daemon import EventReactorDaemon
from memory.graph_memory import GraphMemory
from models.tools import ToolInput
from tools.event_reactor_toolkit import DaemonAddAlert, DaemonStatus, DaemonWatchDirectory
from tools.skill_creator_toolkit import SkillCreate, SkillList


@pytest.mark.asyncio
async def test_skill_creator_validates_syntax_and_creates_file(tmp_path: Path):
    creator = SkillCreate()
    bad_input = ToolInput(
        tool_name="skill_create",
        parameters={
            "skill_name": "test_bad_syntax",
            "description": "Invalid Python",
            "code": "def invalid_py(:",
        },
    )
    result = await creator.execute(bad_input)
    assert result.status.value == "failure"
    assert "syntax error" in (result.error or result.result).lower()

    valid_code = """
from tools.base import BaseTool
from models.tools import ToolInput, ToolOutput

class CustomTestTool(BaseTool):
    name = "custom_test_tool"
    description = "Test custom tool"
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        return self._success("custom_ok")
"""
    good_input = ToolInput(
        tool_name="skill_create",
        parameters={
            "skill_name": "test_good_skill",
            "description": "Valid Python",
            "code": valid_code,
        },
    )
    res_good = await creator.execute(good_input)
    assert res_good.status.value == "success"


@pytest.mark.asyncio
async def test_skill_list_executes():
    lister = SkillList()
    inp = ToolInput(tool_name="skill_list", parameters={})
    res = await lister.execute(inp)
    assert res.status.value == "success"
    assert "skills" in res.data


@pytest.mark.asyncio
async def test_graph_memory_store_and_query(tmp_path: Path):
    db_file = tmp_path / "test_graph.db"
    graph = GraphMemory(db_path=db_file)
    await graph.initialize()

    rowid = await graph.add_relation("OmniCore", "uses", "ChromaDB")
    assert rowid >= 0

    relations = await graph.query_relations("OmniCore")
    assert len(relations) == 1
    assert relations[0]["subject"] == "OmniCore"
    assert relations[0]["predicate"] == "uses"
    assert relations[0]["object"] == "ChromaDB"

    formatted = await graph.format_graph_for_prompt("OmniCore veritabanı")
    assert "OmniCore" in formatted
    assert "ChromaDB" in formatted

    await graph.close()


@pytest.mark.asyncio
async def test_daemon_watch_and_alerts(tmp_path: Path):
    daemon = EventReactorDaemon.get_instance()
    daemon.add_directory_watcher("tmp_watcher", tmp_path)
    daemon.add_metric_alert("cpu", 95.0)

    status = daemon.get_status()
    assert status["watcher_count"] >= 1
    assert status["alert_count"] >= 1

    watch_tool = DaemonWatchDirectory()
    res = await watch_tool.execute(
        ToolInput(
            tool_name="daemon_watch_directory",
            parameters={"path": str(tmp_path), "name": "test_dir"},
        )
    )
    assert res.status.value == "success"

    alert_tool = DaemonAddAlert()
    res_alert = await alert_tool.execute(
        ToolInput(
            tool_name="daemon_add_alert",
            parameters={"metric": "ram", "threshold": 92.0},
        )
    )
    assert res_alert.status.value == "success"

    status_tool = DaemonStatus()
    res_status = await status_tool.execute(ToolInput(tool_name="daemon_status", parameters={}))
    assert res_status.status.value == "success"
    assert res_status.data["alert_count"] >= 2
