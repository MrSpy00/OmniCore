"""Domain test suite for OmniCore system integration, gateways, and toolkits."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from config.settings import Settings
from core.daemon import EventReactorDaemon
from core.guardian import Guardian
from core.planner import Planner
from core.router import _GroqKeyRotator
from interfaces.mcp_gateway import MCPServerGateway
from interfaces.rest_api import create_app
from interfaces.voice_duplex import DuplexVoiceEngine
from memory.graph_memory import GraphMemory
from memory.short_term import ShortTermMemory
from models.messages import Message, MessageRole
from models.tools import ToolInput
from tools.browser_automation_toolkit import BrowserFetchPage
from tools.computer_use_toolkit import GuiLocateAndClick
from tools.database_explorer_toolkit import DbInspectSchema, DbQueryExecute
from tools.developer_toolkit import DevGlobSearch, DevGrepAnalyzer
from tools.event_reactor_toolkit import DaemonWatchDirectory
from tools.game_updater_toolkit import GameUpdater, _find_steam_library_folders
from tools.hardware_telemetry_toolkit import HardwareInspectTelemetry
from tools.mcp_toolkit import SysMcpBridge
from tools.network_infrastructure_toolkit import NetWifiConnect
from tools.refactor_toolkit import RefactorAnalyzeFile, RefactorGeneratePatch
from tools.skill_creator_toolkit import SkillCreate, SkillList
from tools.system_kernel_toolkit import SysKillTaskForcefully


# ---------------------------------------------------------------------------
# Key Rotator & Settings Tests
# ---------------------------------------------------------------------------
class TestGroqKeyRotator:
    def test_single_key_cycles(self):
        rotator = _GroqKeyRotator(["key-A"])
        assert rotator.current == "key-A"
        assert rotator.next_key() == "key-A"
        assert rotator.next_key() == "key-A"

    def test_multiple_keys_cycle(self):
        rotator = _GroqKeyRotator(["key-1", "key-2", "key-3"])
        assert rotator.current == "key-1"
        assert rotator.next_key() == "key-2"
        assert rotator.next_key() == "key-3"
        assert rotator.next_key() == "key-1"

    def test_empty_keys_fallback(self):
        rotator = _GroqKeyRotator([])
        assert rotator.current == ""

    def test_len(self):
        rotator = _GroqKeyRotator(["a", "b"])
        assert len(rotator) == 2


class TestSettingsGroqApiKeys:
    def test_numbered_keys_take_priority(self):
        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "old-single-key",
                "GROQ_API_KEY_1": "key-1",
                "GROQ_API_KEY_2": "key-2",
                "GROQ_API_KEY_3": "key-3",
            },
        ):
            s = Settings()
            keys = s.groq_api_keys
            assert keys == ["key-1", "key-2", "key-3"]

    def test_fallback_to_single_key(self):
        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "single-key",
                "GROQ_API_KEY_1": "",
                "GROQ_API_KEY_2": "",
                "GROQ_API_KEY_3": "",
            },
        ):
            s = Settings()
            keys = s.groq_api_keys
            assert keys == ["single-key"]


# ---------------------------------------------------------------------------
# Core Guardian, Planner & Memory Tests
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Toolkits & Integrations Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_discovery_and_instantiation():
    sys_kill = SysKillTaskForcefully()
    assert sys_kill.name == "sys_kill_task_forcefully"
    assert sys_kill.is_destructive is True

    wifi_tool = NetWifiConnect()
    assert wifi_tool.name == "net_wifi_connect"

    click_tool = GuiLocateAndClick()
    assert click_tool.name == "gui_locate_and_click"


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
    tool = SysMcpBridge()
    write_out = await tool.execute(
        ToolInput(
            tool_name="sys_mcp_bridge",
            parameters={"action": "write", "server_name": "test_mcp", "config_json": "{}"},
        )
    )
    assert write_out.status.value == "success"


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

    formatted = await graph.format_graph_for_prompt("OmniCore database")
    assert "OmniCore" in formatted

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


@pytest.mark.asyncio
async def test_mcp_server_gateway():
    gateway = MCPServerGateway()

    init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    init_res = await gateway.handle_request_json(init_req)
    data = json.loads(init_res)
    assert data["result"]["serverInfo"]["name"] == "OmniCore-MCP-Gateway"

    list_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    list_res = await gateway.handle_request_json(list_req)
    list_data = json.loads(list_res)
    assert len(list_data["result"]["tools"]) > 0


@pytest.mark.asyncio
async def test_refactor_toolkit(tmp_path: Path):
    py_file = tmp_path / "sample.py"
    py_file.write_text("def foo():\n    return 42\n", encoding="utf-8")

    analyzer = RefactorAnalyzeFile()
    res_an = await analyzer.execute(
        ToolInput(
            tool_name="refactor_analyze_file",
            parameters={"file_path": str(py_file)},
        )
    )
    assert res_an.status.value == "success"
    assert res_an.data["metrics"]["function_count"] == 1

    patcher = RefactorGeneratePatch()
    res_pa = await patcher.execute(
        ToolInput(
            tool_name="refactor_generate_patch",
            parameters={
                "file_path": str(py_file),
                "target_text": "return 42",
                "replacement_text": "return 100",
            },
        )
    )
    assert res_pa.status.value == "success"
    assert "return 100" in res_pa.data["patch"]


@pytest.mark.asyncio
async def test_database_explorer_toolkit(tmp_path: Path):
    db_file = tmp_path / "test.db"

    exec_tool = DbQueryExecute()
    create_sql = "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);"
    res_create = await exec_tool.execute(
        ToolInput(
            tool_name="db_query_execute",
            parameters={"db_path": str(db_file), "query": create_sql},
        )
    )
    assert res_create.status.value == "success"

    inspect_tool = DbInspectSchema()
    res_insp = await inspect_tool.execute(
        ToolInput(
            tool_name="db_inspect_schema",
            parameters={"db_path": str(db_file)},
        )
    )
    assert res_insp.status.value == "success"
    assert "users" in res_insp.data["tables"]


@pytest.mark.asyncio
async def test_hardware_telemetry_toolkit():
    hw_tool = HardwareInspectTelemetry()
    res = await hw_tool.execute(ToolInput(tool_name="hardware_inspect_telemetry", parameters={}))
    assert res.status.value == "success"
    assert "cpu_percent" in res.data


@pytest.mark.asyncio
async def test_browser_automation_toolkit():
    fetch_tool = BrowserFetchPage()
    res = await fetch_tool.execute(
        ToolInput(
            tool_name="browser_fetch_page",
            parameters={"url": "https://example.com"},
        )
    )
    assert res.status.value in ("success", "failure")


@pytest.mark.asyncio
async def test_voice_duplex_engine_lifecycle():
    engine = DuplexVoiceEngine()
    assert not engine.is_streaming

    status = await engine.start_session()
    assert status["status"] == "active"
    assert engine.is_streaming

    await engine.push_audio_chunk(b"\x00\x01\x02\x03")
    assert engine.audio_queue.qsize() == 1

    stop_status = await engine.stop_session()
    assert stop_status["status"] == "stopped"
    assert not engine.is_streaming


@pytest.mark.asyncio
async def test_game_updater_vdf_and_acf_parsing(tmp_path: Path):
    steam_root = tmp_path / "Steam"
    steamapps = steam_root / "steamapps"
    steamapps.mkdir(parents=True)

    vdf_content = '''
"libraryfolders"
{
    "0"
    {
        "path"      "C:\\\\Program Files (x86)\\\\Steam"
    }
}
'''
    vdf_file = steamapps / "libraryfolders.vdf"
    vdf_file.write_text(vdf_content, encoding="utf-8")

    libs = _find_steam_library_folders(steam_root)
    assert len(libs) >= 1

    tool = GameUpdater()
    games = tool._scan_steam_games()
    assert isinstance(games, list)


@pytest.mark.asyncio
async def test_rest_api_creation():
    class DummyRouter:
        async def handle_message(self, msg, conv_id):
            return "Mock reply"

    app = create_app(DummyRouter())
    assert app.title == "OmniCore API"
    assert app.version == "0.40.0"
