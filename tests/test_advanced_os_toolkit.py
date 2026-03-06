from __future__ import annotations

import pytest

from models.tools import ToolInput, ToolStatus
from tools.advanced_os_toolkit import OsLaunchApplication


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
