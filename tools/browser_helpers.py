"""Shared Playwright browser launcher — uses user's default browser (Chrome/Edge)."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


def _detect_user_browser() -> str:
    """Detect the user's default browser and return Playwright channel name."""
    if sys.platform == "win32":
        # Check Chrome first, then Edge
        chrome_paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        edge_paths = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                return "chrome"
        for p in edge_paths:
            if os.path.exists(p):
                return "msedge"
    elif sys.platform == "darwin":
        return "chrome"
    return "chromium"  # Fallback to bundled Chromium


async def launch_user_browser(headless: bool = False) -> Any:
    """Launch the user's default browser via Playwright.

    Returns (browser, page) tuple. Caller must close browser when done.
    """
    from playwright.async_api import async_playwright

    channel = _detect_user_browser()
    logger.info("browser.launch", channel=channel, headless=headless)

    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=headless,
        channel=channel,
    )
    page = await browser.new_page()
    return p, browser, page


async def smart_youtube_play(page: Any, query: str) -> dict[str, Any]:
    """Smart YouTube: search, find video, navigate, handle ads, play.

    Returns dict with url, title, status.
    """
    import urllib.parse

    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={urllib.parse.quote_plus(query)}"
    )

    # Navigate to search
    await page.goto(search_url, timeout=30000)
    await page.wait_for_selector("ytd-video-renderer", timeout=15000)

    # Find first video
    first_video = await page.query_selector(
        "ytd-video-renderer a#video-title"
    )
    if not first_video:
        return {"success": False, "error": f"'{query}' için video bulunamadı"}

    href = await first_video.get_attribute("href")
    title = await first_video.inner_text()
    video_url = f"https://www.youtube.com{href}"

    # Navigate to video
    await page.goto(video_url, timeout=30000)

    # Smart: wait for video player to load
    try:
        await page.wait_for_selector(
            "video.html5-main-video, video", timeout=10000
        )
    except Exception:
        pass

    # Smart: try to click play button
    try:
        play_btn = await page.query_selector(
            "button.ytp-large-play-button, "
            "button.ytp-play-button"
        )
        if play_btn:
            await asyncio.sleep(0.3)
            await play_btn.click()
    except Exception:
        pass

    # Smart: skip ad if present (wait up to 8 seconds for ad)
    await _smart_skip_youtube_ad(page)

    return {
        "success": True,
        "url": video_url,
        "title": title.strip(),
        "status": "playing",
    }


async def _smart_skip_youtube_ad(page: Any) -> bool:
    """Detect and skip YouTube ads automatically."""
    # Wait for ad to potentially appear
    for _ in range(20):  # Check every 0.5s for 10 seconds
        try:
            # Check if ad is playing
            ad_showing = await page.query_selector(
                ".ad-showing, .ytp-ad-player-overlay"
            )
            if not ad_showing:
                # No ad — check if there's a skip button from a previous ad
                break

            # Try to click "Skip Ad" button
            skip_btn = await page.query_selector(
                ".ytp-skip-ad-button, "
                "button.ytp-ad-skip-button, "
                ".ytp-ad-skip-button-modern, "
                "button[class*='skip']"
            )
            if skip_btn:
                await skip_btn.click()
                logger.info("youtube.ad_skipped")
                await asyncio.sleep(1)
                return True

            # Try "Skip" text button
            skip_text = await page.query_selector(
                "button:has-text('Atla'), "
                "button:has-text('Skip'), "
                ".ytp-ad-skip-button-slot button"
            )
            if skip_text:
                await skip_text.click()
                logger.info("youtube.ad_skipped_text")
                await asyncio.sleep(1)
                return True
        except Exception:
            pass
        await asyncio.sleep(0.5)

    return False


async def smart_youtube_channel_and_play(
    page: Any, channel_name: str
) -> dict[str, Any]:
    """Navigate to a YouTube channel and play the latest video."""
    import urllib.parse

    # Search for the channel
    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={urllib.parse.quote_plus(channel_name)}"
        "&sp=EgIQAg%3D%3D"  # Channel filter
    )
    await page.goto(search_url, timeout=30000)
    await page.wait_for_selector("ytd-channel-renderer", timeout=15000)

    # Click first channel result
    channel_link = await page.query_selector(
        "ytd-channel-renderer a#channel-title, "
        "ytd-channel-renderer a.yt-simple-endpoint"
    )
    if not channel_link:
        return {
            "success": False,
            "error": f"'{channel_name}' kanalı bulunamadı",
        }

    await channel_link.click()
    await page.wait_for_load_state("domcontentloaded")

    # Navigate to Videos tab
    try:
        videos_tab = await page.query_selector(
            'tp-yt-paper-tab:has-text("Videolar"), '
            'a[href*="/videos"]'
        )
        if videos_tab:
            await videos_tab.click()
            await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    # Find first video
    first_video = await page.query_selector(
        "ytd-rich-item-renderer a#video-title-link, "
        "ytd-grid-video-renderer a#video-title"
    )
    if not first_video:
        return {
            "success": False,
            "error": f"'{channel_name}' kanalında video bulunamadı",
        }

    href = await first_video.get_attribute("href")
    title = await first_video.inner_text()
    video_url = f"https://www.youtube.com{href}"

    # Navigate to video and play
    await page.goto(video_url, timeout=30000)
    try:
        await page.wait_for_selector(
            "video.html5-main-video, video", timeout=10000
        )
    except Exception:
        pass

    # Click play
    try:
        play_btn = await page.query_selector(
            "button.ytp-large-play-button"
        )
        if play_btn:
            await asyncio.sleep(0.3)
            await play_btn.click()
    except Exception:
        pass

    await _smart_skip_youtube_ad(page)

    return {
        "success": True,
        "url": video_url,
        "title": title.strip(),
        "channel": channel_name,
        "status": "playing",
    }
