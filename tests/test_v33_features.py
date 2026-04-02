from __future__ import annotations

from pathlib import Path

import pytest

from core.guardian import Guardian
from core.planner import Planner
from core.router import CognitiveRouter
from memory.short_term import ShortTermMemory
from models.messages import Message, MessageRole
from models.tools import ToolInput
from tools.developer_toolkit import AgentSpawnSubtask, DevGlobSearch, DevGrepAnalyzer
from tools.mcp_toolkit import SysMcpBridge
from tools.registry import ToolRegistry


class _DummyRecovery:
    async def execute_with_retry(self, tool, tool_input, _step):
        return await tool.execute(tool_input)


class _DummyLongTerm:
    def recall(self, _query, n_results=5, where=None):
        return []


@pytest.mark.asyncio
async def test_guardian_plan_mode_toggle():
    guardian = Guardian()
    assert guardian.plan_mode is False
    assert guardian.set_plan_mode(True) is True
    assert guardian.plan_mode is True


def test_short_term_memory_compression_snapshots():
    stm = ShortTermMemory(max_messages=2)
    for i in range(4):
        stm.add_message(
            "conv",
            Message(role=MessageRole.USER, content=f"message-{i}"),
        )

    snapshots = stm.get_compressed_snapshots("conv")
    assert len(snapshots) >= 1
    assert "message-0" in snapshots[0]


def test_planner_marks_delegated_steps():
    planner = Planner(llm=None)  # type: ignore[arg-type]
    plan = planner.build_plan(
        "find references",
        [
            {
                "tool": "dev_grep_analyzer",
                "description": "Search for TODO markers in code",
                "parameters": {"pattern": "TODO"},
            }
        ],
    )
    assert plan.steps[0].delegated is True
    assert plan.steps[0].delegation_strategy == "swarm"


@pytest.mark.asyncio
async def test_dev_glob_and_grep_tools(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    a = root / "a.py"
    b = root / "b.txt"
    a.write_text("print('hello')\n# TODO: fix\n", encoding="utf-8")
    b.write_text("plain text\n", encoding="utf-8")

    glob_tool = DevGlobSearch()
    glob_out = await glob_tool.execute(
        ToolInput(
            tool_name="dev_glob_search",
            parameters={"path": str(root), "pattern": "**/*.py"},
        )
    )
    assert glob_out.status.value == "success"
    assert any(str(a) == item for item in glob_out.data["files"])

    grep_tool = DevGrepAnalyzer()
    grep_out = await grep_tool.execute(
        ToolInput(
            tool_name="dev_grep_analyzer",
            parameters={"path": str(root), "pattern": "TODO", "include": "*.py"},
        )
    )
    assert grep_out.status.value == "success"
    assert grep_out.data["match_count"] >= 1


@pytest.mark.asyncio
async def test_mcp_bridge_read_write(tmp_path: Path):
    bridge_path = tmp_path / "mcp_bridge.json"
    tool = SysMcpBridge()

    write_out = await tool.execute(
        ToolInput(
            tool_name="sys_mcp_bridge",
            parameters={"action": "write", "path": str(bridge_path), "payload": {"ok": True}},
        )
    )
    assert write_out.status.value == "success"

    read_out = await tool.execute(
        ToolInput(
            tool_name="sys_mcp_bridge",
            parameters={"action": "read", "path": str(bridge_path)},
        )
    )
    assert read_out.status.value == "success"
    assert read_out.data["payload"]["ok"] is True


@pytest.mark.asyncio
async def test_router_handles_slash_commands():
    router = CognitiveRouter.__new__(CognitiveRouter)
    router._guardian = Guardian()
    registry = ToolRegistry()
    registry.register(DevGlobSearch())
    registry.register(DevGrepAnalyzer())
    registry.register(AgentSpawnSubtask())
    router._registry = registry
    router._runtime_provider = "gemini"
    router._long_term = _DummyLongTerm()
    router._short_term = ShortTermMemory(max_messages=5)
    router._recovery = _DummyRecovery()

    plan_msg = Message(role=MessageRole.USER, content="/plan", user_id="u1")
    plan_reply = await router._handle_slash_command(plan_msg)
    assert plan_reply is not None
    assert "Plan mode" in plan_reply

    doctor_msg = Message(role=MessageRole.USER, content="/doctor", user_id="u1")
    doctor_reply = await router._handle_slash_command(doctor_msg)
    assert doctor_reply is not None
    assert "provider=" in doctor_reply
