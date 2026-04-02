from __future__ import annotations

import pytest

from core.router import (
    _GROQ_PREEMPTIVE_TOKEN_LIMIT,
    _MAX_RELEVANT_TOOLS,
    CognitiveRouter,
)
from models.tools import ToolInput, ToolStatus
from tools.computer_use_toolkit import GuiLocateAndClick
from tools.os_toolkit import OsDeleteFile, OsWriteFile


def test_v35_router_limits_are_hardened():
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


def test_v35_system_prompt_contains_mark_xxxv_rules():
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
    assert "dev_glob_search" in prompt
    assert "dev_grep_analyzer" in prompt


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
    result = await tool.execute(
        ToolInput(
            tool_name="gui_locate_and_click",
            parameters={"image_path": "Desktop/icon.png", "confidence": 0.9},
        )
    )
    assert result.status == ToolStatus.FAILURE
    assert "opencv-python" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_os_write_file_rejects_placeholder_windows_user_path(monkeypatch, tmp_workspace):
    from config.settings import get_settings

    monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
    get_settings.cache_clear()

    tool = OsWriteFile()
    result = await tool.execute(
        ToolInput(
            tool_name="os_write_file",
            parameters={"path": r"C:\Users\Kullanıcı\Desktop\x.txt", "content": "abc"},
        )
    )

    assert result.status == ToolStatus.FAILURE
    assert "goreli" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_os_delete_file_rejects_placeholder_windows_user_path(monkeypatch, tmp_workspace):
    from config.settings import get_settings

    monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
    get_settings.cache_clear()

    tool = OsDeleteFile()
    result = await tool.execute(
        ToolInput(
            tool_name="os_delete_file",
            parameters={"path": r"C:\Users\Kullanıcı\Desktop\x.txt", "dry_run": False},
        )
    )

    assert result.status == ToolStatus.FAILURE
    assert "goreli" in (result.error or "").lower()


def test_preemptive_route_switches_on_4001_tokens():
    router = CognitiveRouter.__new__(CognitiveRouter)
    router._runtime_provider = "groq"
    switched: list[tuple[str, str]] = []

    def _switch(provider: str, *, reason: str = "runtime") -> bool:
        switched.append((provider, reason))
        router._runtime_provider = provider
        return True

    router._switch_provider = _switch  # type: ignore[method-assign]
    router._maybe_preemptive_gemini_route(estimated_tokens=4001)

    assert router._runtime_provider == "gemini"
    assert switched
    assert switched[0][0] == "gemini"
