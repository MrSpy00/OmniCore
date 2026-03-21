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
            return b"ok", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
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
