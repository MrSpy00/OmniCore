"""Tests for OmniCore v0.39.0 multi-agent swarm, HUD, voice, security, and platform adapter."""

from __future__ import annotations

import pytest

from core.platform_adapter import PlatformAdapter
from core.swarm import AgentSwarmManager
from interfaces.hud import generate_cyberpunk_hud_panel
from interfaces.voice_duplex import DuplexVoiceEngine
from models.tools import ToolInput
from tools.security_audit_toolkit import SecurityAuditSystem, SecurityCveLookup, SecurityPortScan
from tools.swarm_toolkit import SwarmCollectResults, SwarmListAgents, SwarmSpawnAgent


@pytest.mark.asyncio
async def test_agent_swarm_manager_and_tools():
    manager = AgentSwarmManager.get_instance()
    task_id = manager.spawn_subagent("TestRole", "Analyze test data")
    assert task_id.startswith("swarm-")

    res = manager.get_subagent_result(task_id)
    assert res is not None
    assert res["role"] == "TestRole"

    spawn_tool = SwarmSpawnAgent()
    res_spawn = await spawn_tool.execute(
        ToolInput(
            tool_name="swarm_spawn_agent",
            parameters={"role": "Researcher", "prompt": "Search AI papers"},
        )
    )
    assert res_spawn.status.value == "success"
    new_task_id = res_spawn.data["task_id"]

    list_tool = SwarmListAgents()
    res_list = await list_tool.execute(ToolInput(tool_name="swarm_list_agents", parameters={}))
    assert res_list.status.value == "success"
    assert res_list.data["count"] >= 2

    collect_tool = SwarmCollectResults()
    res_coll = await collect_tool.execute(
        ToolInput(
            tool_name="swarm_collect_results",
            parameters={"task_id": new_task_id},
        )
    )
    assert res_coll.status.value == "success"


def test_cyberpunk_hud_panel_generation():
    hud = generate_cyberpunk_hud_panel(
        router_provider="gemini",
        memory_nodes=12,
        active_daemons=2,
        tools_count=45,
    )
    assert "TELEMETRY HUD" in hud
    assert "GEMINI" in hud
    assert "12 nodes" in hud


@pytest.mark.asyncio
async def test_duplex_voice_engine():
    engine = DuplexVoiceEngine()
    start_res = await engine.start_session()
    assert start_res["status"] == "active"
    assert engine.is_streaming is True

    await engine.push_audio_chunk(b"\x00\x01\x02")
    assert engine.audio_queue.qsize() == 1

    stop_res = await engine.stop_session()
    assert stop_res["status"] == "stopped"
    assert engine.is_streaming is False


@pytest.mark.asyncio
async def test_security_audit_toolkit():
    scan_tool = SecurityPortScan()
    res_scan = await scan_tool.execute(
        ToolInput(
            tool_name="security_port_scan",
            parameters={"target": "127.0.0.1", "ports": "80,443"},
        )
    )
    assert res_scan.status.value == "success"

    audit_tool = SecurityAuditSystem()
    inp = ToolInput(tool_name="security_audit_system", parameters={})
    res_audit = await audit_tool.execute(inp)
    assert res_audit.status.value == "success"
    assert "os" in res_audit.data

    cve_tool = SecurityCveLookup()
    res_cve = await cve_tool.execute(
        ToolInput(
            tool_name="security_cve_lookup",
            parameters={"software": "python"},
        )
    )
    assert res_cve.status.value == "success"
    assert res_cve.data["software"] == "python"


def test_platform_adapter():
    os_type = PlatformAdapter.get_os_type()
    assert os_type in {"windows", "linux", "macos"}

    summary = PlatformAdapter.get_system_summary()
    assert "python_version" in summary

    shell = PlatformAdapter.get_default_shell()
    assert shell in {"powershell", "bash"}
