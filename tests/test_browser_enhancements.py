"""Unit tests for Browser Helpers, YouTube Enhancements, and Router Providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import AVAILABLE_PROVIDERS, OPENAI_COMPATIBLE_PROVIDERS
from core.router import _SUPPORTED_PROVIDERS
from models.tools import ToolInput
from tools.advanced_os_toolkit import WebPlayYoutubeVideoVisible
from tools.browser_helpers import (
    _detect_user_browser,
    _parse_relative_date_to_days,
    _parse_time_to_seconds,
    get_browser_session,
    youtube_seek,
)


def test_parse_relative_date_to_days():
    # Turkish relative dates
    assert _parse_relative_date_to_days("3 gün önce") == 3.0
    assert _parse_relative_date_to_days("1 gun once") == 1.0
    assert _parse_relative_date_to_days("2 hafta önce") == 14.0
    assert _parse_relative_date_to_days("1 ay önce") == 30.0
    assert _parse_relative_date_to_days("1 yıl önce") == 365.0
    assert _parse_relative_date_to_days("dün") == 1.0
    assert _parse_relative_date_to_days("bugün") == 0.0

    # English relative dates
    assert _parse_relative_date_to_days("5 days ago") == 5.0
    assert _parse_relative_date_to_days("2 weeks ago") == 14.0
    assert _parse_relative_date_to_days("1 month ago") == 30.0
    assert _parse_relative_date_to_days("yesterday") == 1.0
    assert _parse_relative_date_to_days("today") == 0.0

    # Hours
    hrs = _parse_relative_date_to_days("6 saat önce")
    assert hrs is not None and 0.24 <= hrs <= 0.26


def test_parse_time_to_seconds():
    assert _parse_time_to_seconds("1:30") == 90.0
    assert _parse_time_to_seconds("10:25") == 625.0
    assert _parse_time_to_seconds("1:30:00") == 5400.0
    assert _parse_time_to_seconds("90") == 90.0
    assert _parse_time_to_seconds("2 dakika") == 120.0
    assert _parse_time_to_seconds("45 saniye") == 45.0
    assert _parse_time_to_seconds("1 dk 30 sn") == 90.0


def test_detect_user_browser():
    info = _detect_user_browser()
    assert info.engine in ("chromium", "firefox", "webkit")
    assert info.name is not None
    assert len(info.name) > 0


@pytest.mark.asyncio
async def test_global_browser_session_singleton():
    s1 = await get_browser_session()
    s2 = await get_browser_session()
    assert s1 is s2


@pytest.mark.asyncio
async def test_youtube_seek_relative_middle():
    mock_page = MagicMock()
    # Mock duration evaluate
    mock_page.evaluate = AsyncMock(side_effect=[
        120.0,  # wait_for duration
        120.0,  # duration query
        None,   # seek execution
        False,  # ad showing check
    ])
    mock_page.query_selector = AsyncMock(return_value=None)

    result = await youtube_seek(mock_page, "orta")
    assert result["success"] is True
    assert result["action"] == "seek"
    assert result["time"] == "1:00"  # 120 / 2 = 60s = 1:00
    assert result["seconds"] == 60.0


def test_router_supported_providers_expansion():
    # Verify router includes all 30+ providers
    assert len(_SUPPORTED_PROVIDERS) >= 28
    for expected in (
        "groq",
        "gemini",
        "openai",
        "anthropic",
        "deepseek",
        "mistral",
        "ollama",
        "xai",
        "cohere",
        "ai21",
        "perplexity",
        "reka",
        "writer",
        "fireworks",
        "together",
        "deepinfra",
        "cerebras",
        "moonshot",
        "zhipu",
    ):
        assert expected in _SUPPORTED_PROVIDERS
        assert expected in AVAILABLE_PROVIDERS


def test_openai_compatible_providers_urls():
    for p in ("xai", "cohere", "ai21", "perplexity", "reka", "writer", "together", "fireworks"):
        assert p in OPENAI_COMPATIBLE_PROVIDERS
        assert OPENAI_COMPATIBLE_PROVIDERS[p].startswith("https://")


@pytest.mark.asyncio
async def test_web_play_youtube_video_visible_metadata_action():
    tool = WebPlayYoutubeVideoVisible()
    mock_page = MagicMock()
    mock_page.url = "https://www.youtube.com/watch?v=123"

    mock_meta = {
        "success": True,
        "title": "Test Başlık",
        "channel": "Test Kanal",
        "upload_date": "2 gün önce",
        "days_ago": 2.0,
        "view_count": "100K",
    }

    with patch("tools.browser_helpers.get_browser_session") as mock_get_sess, \
         patch("tools.browser_helpers.youtube_get_video_metadata", AsyncMock(return_value=mock_meta)):
        mock_session = MagicMock()
        mock_session.get_or_create_page = AsyncMock(return_value=mock_page)
        mock_get_sess.return_value = mock_session

        from models.tools import ToolStatus

        inp = ToolInput(
            tool_name="web_play_youtube_video_visible",
            parameters={"action": "metadata"},
        )
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "Test Başlık" in out.result
        assert "2 gün önce" in out.result


@pytest.mark.asyncio
async def test_web_play_youtube_video_visible_channel_latest_intent():
    tool = WebPlayYoutubeVideoVisible()
    mock_page = MagicMock()
    mock_channel_res = {
        "success": True,
        "title": "Son Video Başlığı",
        "url": "https://www.youtube.com/watch?v=abc",
        "channel": "elraenn",
        "upload_date": "1 gün önce",
        "days_ago": 1.0,
    }

    with patch("tools.browser_helpers.get_browser_session") as mock_get_sess, \
         patch("tools.browser_helpers.smart_youtube_channel_and_play", AsyncMock(return_value=mock_channel_res)):
        mock_session = MagicMock()
        mock_session.get_or_create_page = AsyncMock(return_value=mock_page)
        mock_get_sess.return_value = mock_session

        from models.tools import ToolStatus

        inp = ToolInput(
            tool_name="web_play_youtube_video_visible",
            parameters={"query": "elraenn son videosunu aç"},
        )
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "Son Video Başlığı" in out.result
        assert "1 gün önce" in out.result


@pytest.mark.asyncio
async def test_web_play_youtube_video_visible_seek_intent():
    tool = WebPlayYoutubeVideoVisible()
    mock_page = MagicMock()
    mock_seek_res = {
        "success": True,
        "action": "seek",
        "time": "1:29",
        "total_duration": "10:00",
        "seconds": 89.0,
    }

    with patch("tools.browser_helpers.get_browser_session") as mock_get_sess, \
         patch("tools.browser_helpers.youtube_seek", AsyncMock(return_value=mock_seek_res)):
        mock_session = MagicMock()
        mock_session.get_or_create_page = AsyncMock(return_value=mock_page)
        mock_get_sess.return_value = mock_session

        from models.tools import ToolStatus

        inp = ToolInput(
            tool_name="web_play_youtube_video_visible",
            parameters={"query": "1:29'a al"},
        )
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "1:29" in out.result


def test_persona_auto_learning():
    from config.persona_system import PersonaManager

    pm = PersonaManager()
    _ = pm.learn_from_interaction("browser", "firefox", confidence=0.85, context="test")
    # First time might not update if count < 2
    # Second time with high confidence triggers update
    _ = pm.learn_from_interaction("browser", "firefox", confidence=0.90, context="test")
    assert pm.get_preference("preferred_browser") == "firefox"

    # Reset back to brave for user's preference
    pm.set_preference("preferred_browser", "brave", reason="test_reset")
    assert pm.get_preference("preferred_browser") == "brave"


@pytest.mark.asyncio
async def test_dashboard_assets_and_favicon():
    from fastapi.testclient import TestClient

    from interfaces.dashboard import create_dashboard_app

    app = create_dashboard_app()
    client = TestClient(app)

    # Test favicon endpoint returns valid response
    resp = client.get("/favicon.ico")
    assert resp.status_code == 200

    # Test assets endpoint for OmniCore-bounce.png
    asset_resp = client.get("/assets/OmniCore-bounce.png")
    assert asset_resp.status_code == 200
    assert asset_resp.headers.get("content-type") == "image/png"

