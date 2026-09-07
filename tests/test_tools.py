"""Tests for tool implementations."""

from __future__ import annotations

import pytest

from models.tools import ToolInput, ToolStatus
from tools.api_toolkit import ApiDatetime
from tools.developer_toolkit import AgentSpawnSubtask, DevGlobSearch, DevGrepAnalyzer
from tools.mcp_toolkit import SysMcpBridge
from tools.os_toolkit import OsReadFile, OsWriteFile
from tools.registry import ToolRegistry


class TestToolRegistry:
    def test_register_and_lookup(self):
        registry = ToolRegistry()
        tool = OsReadFile()
        registry.register(tool)

        assert "os_read_file" in registry
        assert registry.get("os_read_file") is tool
        assert len(registry) == 1

    def test_duplicate_registration_raises(self):
        registry = ToolRegistry()
        registry.register(OsReadFile())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(OsReadFile())

    def test_list_tools_returns_metadata(self):
        registry = ToolRegistry()
        registry.register(OsReadFile())
        registry.register(OsWriteFile())
        tools = registry.list_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert "os_read_file" in names
        assert "os_write_file" in names


class TestOsToolkit:
    @pytest.mark.asyncio
    async def test_write_and_read_file(self, tmp_workspace, settings, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
        from config.settings import get_settings

        get_settings.cache_clear()

        writer = OsWriteFile()
        result = await writer.execute(
            ToolInput(
                tool_name="os_write_file",
                parameters={"path": "hello.txt", "content": "Hello, OmniCore!"},
            )
        )
        assert result.status == ToolStatus.SUCCESS

        reader = OsReadFile()
        result = await reader.execute(
            ToolInput(
                tool_name="os_read_file",
                parameters={"path": "hello.txt"},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert "Hello, OmniCore!" in result.data["content"]

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tmp_workspace, settings, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
        from config.settings import get_settings

        get_settings.cache_clear()

        reader = OsReadFile()
        result = await reader.execute(
            ToolInput(
                tool_name="os_read_file",
                parameters={"path": "does_not_exist.txt"},
            )
        )
        assert result.status == ToolStatus.FAILURE

    @pytest.mark.asyncio
    async def test_write_returns_raw_path_and_size(self, tmp_workspace, settings, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
        from config.settings import get_settings

        get_settings.cache_clear()

        writer = OsWriteFile()
        result = await writer.execute(
            ToolInput(
                tool_name="os_write_file",
                parameters={"path": "raw_payload.txt", "content": "abc"},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert "path" in result.data
        assert "bytes_written" in result.data


class TestApiDatetime:
    @pytest.mark.asyncio
    async def test_returns_current_datetime(self):
        tool = ApiDatetime()
        result = await tool.execute(
            ToolInput(
                tool_name="api_datetime",
                parameters={"timezone": "UTC"},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert "iso" in result.data
        assert "UTC" in result.data["timezone"]

    @pytest.mark.asyncio
    async def test_default_timezone_is_istanbul(self):
        tool = ApiDatetime()
        result = await tool.execute(
            ToolInput(
                tool_name="api_datetime",
                parameters={},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert "timezone" in result.data
        assert result.data["timezone"] == "Europe/Istanbul"


class TestV33Tools:
    @pytest.mark.asyncio
    async def test_dev_glob_search(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "x.py").write_text("print('x')\n", encoding="utf-8")
        tool = DevGlobSearch()
        result = await tool.execute(
            ToolInput(
                tool_name="dev_glob_search",
                parameters={"path": str(root), "pattern": "**/*.py"},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert result.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_dev_grep_analyzer(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "x.py").write_text("# TODO\nprint('x')\n", encoding="utf-8")
        tool = DevGrepAnalyzer()
        result = await tool.execute(
            ToolInput(
                tool_name="dev_grep_analyzer",
                parameters={"path": str(root), "pattern": "TODO", "include": "*.py"},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert result.data["match_count"] >= 1

    @pytest.mark.asyncio
    async def test_sys_mcp_bridge(self, tmp_path):
        path = tmp_path / "bridge.json"
        tool = SysMcpBridge()
        write_result = await tool.execute(
            ToolInput(
                tool_name="sys_mcp_bridge",
                parameters={"action": "write", "path": str(path), "payload": {"a": 1}},
            )
        )
        assert write_result.status == ToolStatus.SUCCESS

        read_result = await tool.execute(
            ToolInput(
                tool_name="sys_mcp_bridge",
                parameters={"action": "read", "path": str(path)},
            )
        )
        assert read_result.status == ToolStatus.SUCCESS
        assert read_result.data["payload"]["a"] == 1

    @pytest.mark.asyncio
    async def test_agent_spawn_subtask(self):
        tool = AgentSpawnSubtask()
        result = await tool.execute(
            ToolInput(
                tool_name="agent_spawn_subtask",
                parameters={"objective": "Find TODO and search references", "max_subtasks": 3},
            )
        )
        assert result.status == ToolStatus.SUCCESS
        assert result.data["subtask_count"] >= 1
