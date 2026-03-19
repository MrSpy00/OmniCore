from __future__ import annotations

import pytest

from models.tools import ToolInput, ToolStatus
from tools.advanced_os_toolkit import OsLaunchApplication
from tools.advanced_os_toolkit import MediaControlSpotifyNative


@pytest.mark.asyncio
async def test_launch_application_uses_first_param_value(monkeypatch):
    captured = {}

    def fake_launch(app: str) -> None:
        captured["app"] = app

    monkeypatch.setattr("tools.advanced_os_toolkit._launch_windows_app", fake_launch)

    tool = OsLaunchApplication()
    result = await tool.execute(
        ToolInput(tool_name="os_launch_application", parameters={"foo": "Spotify"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert captured["app"] == "Spotify"


@pytest.mark.asyncio
async def test_launch_application_returns_foreground_payload(monkeypatch):
    monkeypatch.setattr("tools.advanced_os_toolkit._launch_windows_app", lambda app: None)
    monkeypatch.setattr(
        "tools.advanced_os_toolkit.force_window_foreground",
        lambda title, timeout_seconds=5.0: {
            "activated": True,
            "method": "test",
            "matched_title": title,
        },
    )

    tool = OsLaunchApplication()
    result = await tool.execute(
        ToolInput(tool_name="os_launch_application", parameters={"app": "Notepad"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.data.get("foreground", {}).get("activated") is True


@pytest.mark.asyncio
async def test_media_control_spotify_native_runs(monkeypatch):
    monkeypatch.setattr(
        "tools.advanced_os_toolkit._media_control_native",
        lambda action: {"action": action, "stdout": "ok", "stderr": ""},
    )

    tool = MediaControlSpotifyNative()
    result = await tool.execute(
        ToolInput(tool_name="media_control_spotify_native", parameters={"action": "next"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.data.get("action") == "next"
