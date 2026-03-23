from __future__ import annotations

import asyncio

import pytest

from models.tools import ToolInput, ToolStatus
from tools.terminal_toolkit import TerminalExecute


@pytest.mark.asyncio
async def test_terminal_execute_sets_utf8_env(monkeypatch, tmp_path):
    recorded = {}

    class DummyProcess:
        returncode = 0

        async def communicate(self):
            await asyncio.sleep(0)
            return b"ok", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        await asyncio.sleep(0)
        recorded["args"] = args
        recorded.update(kwargs)
        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(
        "tools.terminal_toolkit._build_shell_command",
        lambda command: (["fake-shell", "-c", command], "fake-shell"),
    )

    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": "dir", "cwd": "."})
    )

    assert result.status == ToolStatus.SUCCESS
    assert recorded["env"]["PYTHONIOENCODING"] == "utf-8"
    assert recorded["env"]["PYTHONUTF8"] == "1"
    assert recorded["args"] == ("fake-shell", "-c", "dir")
    assert recorded["cwd"] == str(tmp_path)
    assert result.data["shell"] == "fake-shell"


@pytest.mark.asyncio
async def test_terminal_execute_blocks_dangerous_pattern(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": "rm -rf /"})
    )

    assert result.status == ToolStatus.FAILURE
    assert "blocked by safety policy" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_dry_run_does_not_spawn_process(monkeypatch, tmp_path):
    called = {"value": False}

    async def fake_create_subprocess_exec(*args, **kwargs):
        await asyncio.sleep(0)
        called["value"] = True
        raise AssertionError("process should not be created in dry-run mode")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(
        "tools.terminal_toolkit._build_shell_command",
        lambda command: (["fake-shell", "-c", command], "fake-shell"),
    )
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(
            tool_name="terminal_execute",
            parameters={"command": "Get-Process", "dry_run": True, "cwd": "."},
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.data["dry_run"] is True
    assert result.data["shell"] == "fake-shell"
    assert "command_quality" in result.data
    assert result.data["command_quality"]["safety"] == "readonly"
    assert called["value"] is False


@pytest.mark.asyncio
async def test_terminal_execute_blocks_defensive_only_markers(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": "psexec -s cmd.exe"})
    )

    assert result.status == ToolStatus.FAILURE
    assert "privilege-escalation pattern blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_blocks_fodhelper_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": "fodhelper.exe"})
    )

    assert result.status == ToolStatus.FAILURE
    assert "category: privilege_escalation" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_block_message_contains_matched_marker(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(
            tool_name="terminal_execute",
            parameters={"command": "python -c \"import ctypes; ctypes.CDLL('libc.so.6').ptrace\""},
        )
    )

    assert result.status == ToolStatus.FAILURE
    assert "matched marker: ptrace" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_block_message_contains_category(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": "psexec -s cmd.exe"})
    )

    assert result.status == ToolStatus.FAILURE
    assert "category: privilege_escalation" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_block_message_contains_persistence_category(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    command = "wmic /namespace:\\root\\subscription PATH CommandLineEventConsumer CREATE"
    result = await tool.execute(
        ToolInput(
            tool_name="terminal_execute",
            parameters={"command": command},
        )
    )

    assert result.status == ToolStatus.FAILURE
    assert "category: persistence_abuse" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_block_message_contains_kernel_category(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    command = "bpftrace -e 'tracepoint:syscalls:sys_enter_openat { printf(\"x\") }'"
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": command})
    )

    assert result.status == ToolStatus.FAILURE
    assert "category: kernel_manipulation" in result.error.lower()


@pytest.mark.asyncio
async def test_terminal_execute_block_message_contains_raw_disk_category(monkeypatch, tmp_path):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    tool = TerminalExecute()
    command = "type \\\\.\\PhysicalDrive0"
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": command})
    )

    assert result.status == ToolStatus.FAILURE
    assert "category: raw_disk_access" in result.error.lower()
