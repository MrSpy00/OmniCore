"""Tests for V18 features: round-robin keys, new tools, anti-loop, Turkish prompt."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.router import _GroqKeyRotator


# ---------------------------------------------------------------------------
# Round-robin key rotator
# ---------------------------------------------------------------------------
class TestGroqKeyRotator:
    def test_single_key_cycles(self):
        rotator = _GroqKeyRotator(["key-A"])
        assert rotator.current == "key-A"
        assert rotator.next_key() == "key-A"
        assert rotator.next_key() == "key-A"

    def test_multiple_keys_cycle(self):
        rotator = _GroqKeyRotator(["key-1", "key-2", "key-3"])
        # After init, we're on key-1.
        assert rotator.current == "key-1"
        assert rotator.next_key() == "key-2"
        assert rotator.next_key() == "key-3"
        assert rotator.next_key() == "key-1"  # wraps around

    def test_empty_keys_fallback(self):
        rotator = _GroqKeyRotator([])
        assert rotator.current == ""

    def test_len(self):
        rotator = _GroqKeyRotator(["a", "b"])
        assert len(rotator) == 2


# ---------------------------------------------------------------------------
# Settings multi-key property
# ---------------------------------------------------------------------------
class TestSettingsGroqApiKeys:
    def test_numbered_keys_take_priority(self):
        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "old-single-key",
                "GROQ_API_KEY_1": "key-1",
                "GROQ_API_KEY_2": "key-2",
                "GROQ_API_KEY_3": "key-3",
            },
        ):
            from config.settings import Settings

            s = Settings()
            keys = s.groq_api_keys
            assert keys == ["key-1", "key-2", "key-3"]

    def test_fallback_to_single_key(self):
        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "single-key",
                "GROQ_API_KEY_1": "",
                "GROQ_API_KEY_2": "",
                "GROQ_API_KEY_3": "",
            },
        ):
            from config.settings import Settings

            s = Settings()
            keys = s.groq_api_keys
            assert keys == ["single-key"]


# ---------------------------------------------------------------------------
# New tool discovery (V18 tools exist and load)
# ---------------------------------------------------------------------------
class TestV18ToolDiscovery:
    def test_sys_kill_task_forcefully_loadable(self):
        from tools.system_kernel_toolkit import SysKillTaskForcefully

        tool = SysKillTaskForcefully()
        assert tool.name == "sys_kill_task_forcefully"
        assert tool.is_destructive is True

    def test_net_wifi_connect_loadable(self):
        from tools.network_infrastructure_toolkit import NetWifiConnect

        tool = NetWifiConnect()
        assert tool.name == "net_wifi_connect"
        assert tool.is_destructive is True

    def test_gui_locate_and_click_loadable(self):
        from tools.computer_use_toolkit import GuiLocateAndClick

        tool = GuiLocateAndClick()
        assert tool.name == "gui_locate_and_click"
        assert tool.is_destructive is True

    def test_os_clipboard_history_manager_loadable(self):
        from tools.advanced_os_toolkit import OsClipboardHistoryManager

        tool = OsClipboardHistoryManager()
        assert tool.name == "os_clipboard_history_manager"

    def test_web_play_youtube_video_visible_loadable(self):
        from tools.advanced_os_toolkit import WebPlayYoutubeVideoVisible

        tool = WebPlayYoutubeVideoVisible()
        assert tool.name == "web_play_youtube_video_visible"
        assert tool.is_destructive is True

    def test_sys_force_foreground_loadable(self):
        from tools.advanced_os_toolkit import SysForceForeground

        tool = SysForceForeground()
        assert tool.name == "sys_force_foreground"

    def test_sys_get_all_installed_apps_loadable(self):
        from tools.advanced_os_toolkit import SysGetAllInstalledApps

        tool = SysGetAllInstalledApps()
        assert tool.name == "sys_get_all_installed_apps"

    def test_net_monitor_live_traffic_loadable(self):
        from tools.network_infrastructure_toolkit import NetMonitorLiveTraffic

        tool = NetMonitorLiveTraffic()
        assert tool.name == "net_monitor_live_traffic"

    def test_media_control_spotify_native_loadable(self):
        from tools.advanced_os_toolkit import MediaControlSpotifyNative

        tool = MediaControlSpotifyNative()
        assert tool.name == "media_control_spotify_native"

    def test_web_bypass_cloudflare_loadable(self):
        from tools.deep_web_osint_toolkit import WebBypassCloudflare

        tool = WebBypassCloudflare()
        assert tool.name == "web_bypass_cloudflare"

    def test_os_deep_search_loadable(self):
        from tools.network_infrastructure_toolkit import OsDeepSearch

        tool = OsDeepSearch()
        assert tool.name == "os_deep_search"

    def test_sys_read_notifications_loadable(self):
        from tools.advanced_os_toolkit import SysReadNotifications

        tool = SysReadNotifications()
        assert tool.name == "sys_read_notifications"

    def test_media_screen_record_invisible_loadable(self):
        from tools.computer_use_toolkit import MediaScreenRecordInvisible

        tool = MediaScreenRecordInvisible()
        assert tool.name == "media_screen_record_invisible"


# ---------------------------------------------------------------------------
# Anti-loop hardening (Turkish error messages)
# ---------------------------------------------------------------------------
class TestRecoveryAntiLoop:
    @pytest.mark.asyncio
    async def test_recovery_stops_after_2_failures_with_turkish_error(self):
        from core.recovery import RecoveryEngine
        from models.tasks import TaskStep
        from models.tools import ToolInput, ToolOutput, ToolStatus
        from tools.base import BaseTool

        class AlwaysFailTool(BaseTool):
            name = "always_fail"
            description = "Test tool"

            async def execute(self, tool_input: ToolInput) -> ToolOutput:
                return ToolOutput(
                    tool_name=self.name,
                    status=ToolStatus.FAILURE,
                    error="deliberate failure",
                )

        engine = RecoveryEngine()
        step = TaskStep(
            tool_name="always_fail",
            description="test",
            parameters={},
            max_retries=5,  # Set high — engine should cap at 2
        )
        tool_input = ToolInput(tool_name="always_fail", parameters={})
        output = await engine.execute_with_retry(AlwaysFailTool(), tool_input, step)

        assert output.status == ToolStatus.FAILURE
        assert "DÖNGÜ KORUMASI" in output.error
        assert step.retry_count <= 2


# ---------------------------------------------------------------------------
# Turkish system prompt
# ---------------------------------------------------------------------------
class TestTurkishPrompt:
    def test_prompt_is_turkish(self):
        from typing import Any, cast

        from core.router import CognitiveRouter

        router = CognitiveRouter.__new__(CognitiveRouter)
        router._registry = cast(
            Any,
            type(
                "Registry",
                (),
                {
                    "list_tools": lambda self: [
                        {"name": "test", "description": "test", "destructive": "False"}
                    ]
                },
            )(),
        )
        prompt = router._build_system_prompt("")
        # Must NOT contain English mandate
        assert "CRITICAL MANDATE" not in prompt
        # Must contain Turkish
        assert "OMNICORE" in prompt
        assert "ASLA İNGİLİZCE KONUŞMA" in prompt
