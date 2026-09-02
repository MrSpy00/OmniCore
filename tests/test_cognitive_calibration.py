"""Cognitive Router calibration tests."""

from __future__ import annotations

import pytest

from core.router import (
    _GROQ_PREEMPTIVE_TOKEN_LIMIT,
    _MAX_RELEVANT_TOOLS,
    CognitiveRouter,
)
from models.tools import ToolInput
from tools.computer_use_toolkit import GuiLocateAndClick
from tools.os_toolkit import OsDeleteFile, OsWriteFile


def test_router_limits_are_hardened():
    assert _MAX_RELEVANT_TOOLS == 12
    assert _GROQ_PREEMPTIVE_TOKEN_LIMIT == 4000


def test_filter_relevant_tools_caps_to_12_and_prioritizes_native_media():
    router = CognitiveRouter.__new__(CognitiveRouter)
    tools = [
        {"name": f"dev_tool_{i}", "description": "developer utility", "destructive": "False"}
        for i in range(80)
    ]
    tools.extend(
        [
            {
                "name": "agent_spawn_subtask",
                "description": "spawn delegated subtasks",
                "destructive": "False",
            },
            {
                "name": "terminal_execute",
                "description": "execute shell commands",
                "destructive": "True",
            },
            {
                "name": "os_read_file",
                "description": "read file content",
                "destructive": "False",
            },
            {
                "name": "media_control_native",
                "description": "native media controls",
                "destructive": "False",
            },
            {
                "name": "media_control_spotify_native",
                "description": "spotify media controls",
                "destructive": "False",
            },
            {
                "name": "gui_click_image_on_screen",
                "description": "image click",
                "destructive": "True",
            },
        ]
    )

    selected = router._filter_relevant_tools("spotify muzik oynat", tools)
    names = {t["name"] for t in selected}
    assert len(selected) <= 12
    assert "agent_spawn_subtask" in names
    assert "terminal_execute" in names
    assert "os_read_file" in names
    assert "media_control_native" in names
    assert "media_control_spotify_native" in names


def test_system_prompt_contains_sovereign_rules():
    router = CognitiveRouter.__new__(CognitiveRouter)
    prompt = router._build_system_prompt_with_tools(
        memory_context="memory",
        tools=[{"name": "os_read_file", "description": "read", "destructive": "False"}],
    )
    assert "KURAL 8" in prompt
    assert "media_control_native" in prompt
    assert "media_control_spotify_native" in prompt
    assert "KURAL 9" in prompt
    assert "Desktop/dosya.txt" in prompt
    assert "KURAL 10" in prompt
    assert "agent_spawn_subtask" in prompt or "dogrudan" in prompt.lower()


@pytest.mark.asyncio
async def test_gui_locate_and_click_reports_missing_opencv(monkeypatch, tmp_workspace):
    from config.settings import get_settings

    monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
    get_settings.cache_clear()

    class _Cv2MissingError(RuntimeError):
        pass

    def _raise_missing(*_args, **_kwargs):
        raise _Cv2MissingError("OpenCV support not installed")

    monkeypatch.setattr("tools.computer_use_toolkit.pyautogui.locateCenterOnScreen", _raise_missing)

    tool = GuiLocateAndClick()
    out = await tool.execute(
        ToolInput(
            tool_name="gui_locate_and_click",
            parameters={"image_path": str(tmp_workspace / "icon.png")},
        )
    )
    assert out.status.value == "failure"
    assert "opencv" in out.error.lower() or "not installed" in out.error.lower()


@pytest.mark.asyncio
async def test_destructive_file_operations_refuse_absolute_paths_outside_workspace(
    monkeypatch, tmp_workspace
):
    from config.settings import get_settings

    monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
    get_settings.cache_clear()

    write_tool = OsWriteFile()
    out_write = await write_tool.execute(
        ToolInput(
            tool_name="os_write_file",
            parameters={"path": "C:\\Windows\\System32\\test.txt", "content": "bad"},
        )
    )
    assert out_write.status.value == "failure"

    del_tool = OsDeleteFile()
    out_del = await del_tool.execute(
        ToolInput(
            tool_name="os_delete_file",
            parameters={"path": "C:\\Windows\\System32\\cmd.exe"},
        )
    )
    assert out_del.status.value == "failure"
