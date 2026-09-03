from __future__ import annotations

import os
from pathlib import Path
import pytest

from models.tools import ToolInput, ToolStatus
from tools.base import resolve_user_path, resolve_desktop_path


def test_turkish_path_aliases():
    """Verify Turkish aliases correctly map to user folders."""
    desktop_target, _ = resolve_user_path("masaüstü/screenshot.png")
    assert "Desktop" in str(desktop_target) or "desktop" in str(desktop_target).lower()
    assert desktop_target.name == "screenshot.png"

    downloads_target, _ = resolve_user_path("indirilenler/test.zip")
    assert "Downloads" in str(downloads_target) or "downloads" in str(downloads_target).lower()

    docs_target, _ = resolve_user_path("belgeler/rapor.docx")
    assert "Documents" in str(docs_target) or "documents" in str(docs_target).lower()


def test_resolve_desktop_path_defaults():
    """Verify resolve_desktop_path defaults cleanly to Desktop."""
    # When None or empty
    p1 = resolve_desktop_path()
    assert p1.name == "screenshot.png"
    assert "Desktop" in str(p1) or "desktop" in str(p1).lower()

    # When filename only
    p2 = resolve_desktop_path("my_capture.png")
    assert p2.name == "my_capture.png"
    assert "Desktop" in str(p2) or "desktop" in str(p2).lower()

    # When alias only
    p3 = resolve_desktop_path("masaüstü")
    assert p3.name == "screenshot.png"
    assert "Desktop" in str(p3) or "desktop" in str(p3).lower()


@pytest.mark.asyncio
async def test_computer_use_gui_screenshot_classes(monkeypatch, tmp_path):
    """Verify GuiScreenshot and ScreenCapture exist and execute properly."""
    from tools.computer_use_toolkit import GuiScreenshot, ScreenCapture
    from tools.gui_automation_toolkit import GuiTakeScreenshot

    captured = {}

    async def fake_execute(self, tool_input):
        captured["input"] = tool_input
        return self._success("Screenshot saved", data={"path": str(tmp_path / "screenshot.png")})

    monkeypatch.setattr(GuiTakeScreenshot, "execute", fake_execute)

    tool = GuiScreenshot()
    out = await tool.execute(ToolInput(tool_name="gui_screenshot", parameters={}))
    assert out.status == ToolStatus.SUCCESS

    alias_tool = ScreenCapture()
    assert alias_tool.name == "screen_capture"
    out2 = await alias_tool.execute(ToolInput(tool_name="screen_capture", parameters={}))
    assert out2.status == ToolStatus.SUCCESS


@pytest.mark.asyncio
async def test_browser_launch_tool(monkeypatch):
    """Verify BrowserLaunch handles URL and launches process."""
    from tools.browser_automation_toolkit import BrowserLaunch

    def fake_launch(url, browser):
        return {"success": True, "method": "mock_launch", "url": url}

    monkeypatch.setattr("tools.browser_automation_toolkit._launch_browser_process", fake_launch)

    tool = BrowserLaunch()
    out = await tool.execute(ToolInput(tool_name="browser_launch", parameters={"url": "google.com"}))
    assert out.status == ToolStatus.SUCCESS
    assert "https://google.com" in out.data["url"]


def test_live_config_set_model_for_provider():
    """Verify set_model_for_provider returns tuple[bool, str] with confirmation."""
    from config.live_config import LiveConfig

    lc = LiveConfig()
    success, msg = lc.set_model_for_provider("gemini", "gemini-2.5-flash")
    assert success is True
    assert "Gemini" in msg or "gemini" in msg.lower()
    assert "guncellendi" in msg.lower() or "güncellendi" in msg.lower() or "kaydedildi" in msg.lower()


def test_settings_deprecated_model_validator():
    """Verify deprecated gemini-2.0-flash automatically falls back to 2.5."""
    from config.settings import Settings

    s = Settings(omni_llm_model="gemini-2.0-flash")
    assert s.omni_llm_model == "gemini-2.5-flash"

    s_lite = Settings(omni_llm_model="gemini-2.0-flash-lite")
    assert s_lite.omni_llm_model == "gemini-2.5-flash-lite"
