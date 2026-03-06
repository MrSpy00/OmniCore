from __future__ import annotations

import asyncio

import pytest

from models.tools import ToolInput, ToolStatus
from tools.terminal_toolkit import TerminalExecute


@pytest.mark.asyncio
async def test_terminal_execute_sets_utf8_env(monkeypatch):
    recorded = {}

    class DummyProcess:
        returncode = 0

        async def communicate(self):
            return b"ok", b""

    async def fake_create_subprocess_shell(*args, **kwargs):
        recorded["args"] = args
        recorded.update(kwargs)
        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_create_subprocess_shell)

    tool = TerminalExecute()
    result = await tool.execute(
        ToolInput(tool_name="terminal_execute", parameters={"command": "dir"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert recorded["env"]["PYTHONIOENCODING"] == "utf-8"
    assert recorded["env"]["PYTHONUTF8"] == "1"
    assert recorded["args"][0] == "chcp 65001 >NUL && dir"
