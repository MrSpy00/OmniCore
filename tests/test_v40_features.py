"""Tests for OmniCore v0.40.0 sovereign enterprise features."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interfaces.mcp_gateway import MCPServerGateway
from models.tools import ToolInput
from tools.browser_automation_toolkit import BrowserFetchPage
from tools.database_explorer_toolkit import DbInspectSchema, DbQueryExecute
from tools.hardware_telemetry_toolkit import HardwareInspectTelemetry
from tools.refactor_toolkit import RefactorAnalyzeFile, RefactorGeneratePatch


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
    assert "gpu" in res.data


@pytest.mark.asyncio
async def test_browser_automation_toolkit():
    fetch_tool = BrowserFetchPage()
    res = await fetch_tool.execute(
        ToolInput(
            tool_name="browser_fetch_page",
            parameters={"url": "example.com"},
        )
    )
    assert res.status.value == "success"
    assert "Example Domain" in res.data["text"]
