"""Shared Playwright browser launcher — uses user's default browser."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

if sys.platform == "win32":
    import winreg

from config.logging import get_logger

logger = get_logger(__name__)

# Windows registry handler -> Playwright channel mapping
_HANDLER_TO_CHANNEL: dict[str, str] = {
    "ChromeHTML": "chrome",
    "ChromeSSOHTM": "chrome",
    "MSEdgeHTM": "msedge",
    "MSEdgeHTML": "msedge",
    "BraveHTML": "chrome",  # Brave is Chromium-based, use chrome channel
    "BraveSSOHTM": "chrome",
    "ChromiumHTM": "chrome",
    "FirefoxURL": "firefox",
    "FirefoxHTML": "firefox",
    "TorBrowserURL": "firefox",  # Tor is Firefox-based
    "LibreWolfHTML": "firefox",
    "ZenHTML": "firefox",
    "VivaldiHTML": "chrome",  # Vivaldi is Chromium-based
    "OperaHTML": "chrome",  # Opera is Chromium-based
    "Safari": "webkit",
}

# Browser exe paths to channel mapping (fallback)
_BROWSER_PATHS: list[tuple[str, list[str], str]] = [
    # (channel_name, [exe_paths], priority)
    (
        "chrome",
        [
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
        ],
        1,
    ),
    (
        "msedge",
        [
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        ],
        2,
    ),
    (
        "chrome",
        [  # Brave
            r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        3,
    ),
    (
        "chrome",
        [  # Vivaldi
            r"%LocalAppData%\Vivaldi\Application\vivaldi.exe",
        ],
        4,
    ),
    (
        "chrome",
        [  # Opera
            r"%ProgramFiles%\Opera\opera.exe",
            r"%LocalAppData%\Opera Software\Opera Stable\opera.exe",
        ],
        5,
    ),
    (
        "chrome",
        [  # Chromium
            r"%LocalAppData%\Chromium\Application\chrome.exe",
        ],
        6,
    ),
    (
        "firefox",
        [
            r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
        ],
        7,
    ),
    (
        "firefox",
        [  # LibreWolf
            r"%ProgramFiles%\LibreWolf\librewolf.exe",
            r"%LocalAppData%\LibreWolf\librewolf.exe",
        ],
        8,
    ),
    (
        "firefox",
        [  # Tor Browser
            r"%ProgramFiles%\Tor Browser\Browser\firefox.exe",
            r"%LocalAppData%\Tor Browser\Browser\firefox.exe",
        ],
        9,
    ),
]


def _detect_user_browser() -> str:
    """Detect the user's default browser and return Playwright channel.

    Detection order:
    1. Windows registry (default HTTP handler) — most reliable
    2. File system scan — find installed browsers
    3. Fallback to chromium
    """
    if sys.platform == "win32":
        return _detect_browser_windows()
    elif sys.platform == "darwin":
        return _detect_browser_macos()
    return "chromium"


def _detect_browser_windows() -> str:
    """Detect default browser on Windows via registry + file scan."""
    # Method 1: Registry — default HTTP handler
    try:
        key_path = (
            r"Software\Microsoft\Windows\Shell"
            r"\Associations\UrlAssociations\http\UserChoice"
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
            channel = _HANDLER_TO_CHANNEL.get(str(prog_id))
            if channel:
                logger.info(
                    "browser.detected_registry",
                    prog_id=prog_id,
                    channel=channel,
                )
                return channel
    except (OSError, FileNotFoundError):
        pass

    # Method 2: File system scan — find any installed browser
    for channel, paths, _priority in sorted(_BROWSER_PATHS, key=lambda x: x[2]):
        for path_template in paths:
            path = os.path.expandvars(path_template)
            if os.path.exists(path):
                logger.info("browser.detected_filesystem", path=path, channel=channel)
                return channel

    return "chromium"


def _detect_browser_macos() -> str:
    """Detect default browser on macOS."""
    try:
        import subprocess

        subprocess.run(
            ["open", "-a", "Default Browser", "--args", "--version"],
            capture_output=True,
            timeout=5,
        )
        # Default.app -> check bundle
        default_app = subprocess.run(
            ["defaults", "read", "com.apple.LaunchServices/com.apple.launchservices.secure", "LSHandlers"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = default_app.stdout
        if "chrome" in output.lower():
            return "chrome"
        if "firefox" in output.lower():
            return "firefox"
        if "safari" in output.lower():
            return "webkit"
    except Exception:
        pass
    return "chromium"


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

    search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"

    # Navigate to search
    await page.goto(search_url, timeout=30000)
    await page.wait_for_selector("ytd-video-renderer", timeout=15000)

    # Find first video
    first_video = await page.query_selector("ytd-video-renderer a#video-title")
    if not first_video:
        return {"success": False, "error": f"'{query}' için video bulunamadı"}

    href = await first_video.get_attribute("href")
    title = await first_video.inner_text()
    video_url = f"https://www.youtube.com{href}"

    # Navigate to video
    await page.goto(video_url, timeout=30000)

    # Smart: wait for video player to load
    try:
        await page.wait_for_selector("video.html5-main-video, video", timeout=10000)
    except Exception:
        pass

    # Smart: try to click play button
    try:
        play_btn = await page.query_selector("button.ytp-large-play-button, button.ytp-play-button")
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
            ad_showing = await page.query_selector(".ad-showing, .ytp-ad-player-overlay")
            if not ad_showing:
                # No ad — check if there's a skip button from a previous ad
                break

            # Try to click "Skip Ad" button
            skip_btn = await page.query_selector(
                ".ytp-skip-ad-button, button.ytp-ad-skip-button, .ytp-ad-skip-button-modern, button[class*='skip']"
            )
            if skip_btn:
                await skip_btn.click()
                logger.info("youtube.ad_skipped")
                await asyncio.sleep(1)
                return True

            # Try "Skip" text button
            skip_text = await page.query_selector(
                "button:has-text('Atla'), button:has-text('Skip'), .ytp-ad-skip-button-slot button"
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


async def smart_youtube_channel_and_play(page: Any, channel_name: str) -> dict[str, Any]:
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
        "ytd-channel-renderer a#channel-title, ytd-channel-renderer a.yt-simple-endpoint"
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
        videos_tab = await page.query_selector('tp-yt-paper-tab:has-text("Videolar"), a[href*="/videos"]')
        if videos_tab:
            await videos_tab.click()
            await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass

    # Find first video
    first_video = await page.query_selector(
        "ytd-rich-item-renderer a#video-title-link, ytd-grid-video-renderer a#video-title"
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
        await page.wait_for_selector("video.html5-main-video, video", timeout=10000)
    except Exception:
        pass

    # Click play
    try:
        play_btn = await page.query_selector("button.ytp-large-play-button")
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


# ---------------------------------------------------------------------------
# YouTube Kontrol Fonksiyonlari
# ---------------------------------------------------------------------------


async def youtube_seek(page: Any, time_str: str) -> dict[str, Any]:
    """Seek to a specific time in a YouTube video.

    time_str: "1:30", "10:25", "1:30:00", "orta", "bas", "son", "yuzde50"
    """
    # Parse time string to seconds
    seconds = _parse_time_to_seconds(time_str)
    if seconds is None and time_str.lower() not in ("orta", "bas", "son"):
        return {"success": False, "error": f"Geçersiz zaman: {time_str}"}

    # Get video duration
    duration = await page.evaluate("() => { const v = document.querySelector('video'); return v ? v.duration : 0; }")
    if duration <= 0:
        return {"success": False, "error": "Video oynatıcı bulunamadı veya video henüz yüklenmedi"}

    # Handle relative times
    ts = time_str.lower().strip()
    if ts == "orta":
        seconds = duration / 2
    elif ts == "bas":
        seconds = 0
    elif ts == "son":
        seconds = max(0, duration - 5)
    elif ts.startswith("yuzde") or ts.startswith("%"):
        pct = float(ts.replace("yuzde", "").replace("%", "")) / 100
        seconds = duration * pct

    # Seek
    await page.evaluate(f"() => {{ const v = document.querySelector('video'); if(v) v.currentTime = {seconds}; }}")
    await asyncio.sleep(0.5)

    # Ensure playing
    is_paused = await page.evaluate("() => { const v = document.querySelector('video'); return v ? v.paused : true; }")
    if is_paused:
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")

    await _smart_skip_youtube_ad(page)

    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return {
        "success": True,
        "action": "seek",
        "time": f"{mins}:{secs:02d}",
        "total_duration": f"{int(duration // 60)}:{int(duration % 60):02d}",
    }


async def youtube_control(page: Any, action: str) -> dict[str, Any]:
    """Control YouTube video playback.

    action: play, pause, toggle, fullscreen, mute, unmute, volume_up,
            volume_down, next, previous, speed_up, speed_down, normal_speed,
            pip (picture-in-picture), like, subscribe
    """
    action = action.lower().strip()

    if action in ("play", "devam", "oynat"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
        return {"success": True, "action": "play", "message": "Video oynatılıyor"}

    elif action in ("pause", "duraklat", "dur"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.pause(); }")
        return {"success": True, "action": "pause", "message": "Video duraklatıldı"}

    elif action in ("toggle", "degistir", "oynatduraklat"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); if(v) { v.paused ? v.play() : v.pause(); } }"
        )
        state = await page.evaluate(
            "() => { const v = document.querySelector('video'); "
            "return v ? (v.paused ? 'duraklatildi' : 'oynatiliyor') : 'bulunamadi'; }"
        )
        return {"success": True, "action": "toggle", "message": f"Video {state}"}

    elif action in ("fullscreen", "tam_ekran", "ekran"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); "
            "if(v) { v.requestFullscreen ? v.requestFullscreen() : "
            "v.webkitRequestFullscreen ? v.webkitRequestFullscreen() : null; } }"
        )
        return {"success": True, "action": "fullscreen", "message": "Tam ekran modu"}

    elif action in ("mute", "sessiz"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.muted = true; }")
        return {"success": True, "action": "mute", "message": "Sessize alındı"}

    elif action in ("unmute", "sesli"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.muted = false; }")
        return {"success": True, "action": "unmute", "message": "Ses açıldı"}

    elif action in ("volume_up", "ses_ac", "ses_artir"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); if(v) v.volume = Math.min(1.0, v.volume + 0.1); }"
        )
        vol_js = "() => { const v = document.querySelector('video'); return v ? Math.round(v.volume * 100) : 0; }"
        vol = await page.evaluate(vol_js)
        return {"success": True, "action": "volume_up", "volume": f"%{vol}"}

    elif action in ("volume_down", "ses_kis", "ses_azalt"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); if(v) v.volume = Math.max(0.0, v.volume - 0.1); }"
        )
        vol_js = "() => { const v = document.querySelector('video'); return v ? Math.round(v.volume * 100) : 0; }"
        vol = await page.evaluate(vol_js)
        return {"success": True, "action": "volume_down", "volume": f"%{vol}"}

    elif action in ("next", "sonraki"):
        next_btn = await page.query_selector("a.ytp-next-button, button.ytp-next-button")
        if next_btn:
            await next_btn.click()
            return {"success": True, "action": "next", "message": "Sonraki videoya geçildi"}
        return {"success": False, "error": "Sonraki butonu bulunamadı"}

    elif action in ("previous", "onceki"):
        prev_btn = await page.query_selector("a.ytp-prev-button, button.ytp-prev-button")
        if prev_btn:
            await prev_btn.click()
            return {"success": True, "action": "previous", "message": "Önceki videoya geçildi"}
        return {"success": False, "error": "Önceki butonu bulunamadı"}

    elif action in ("speed_up", "hizlan"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); "
            "if(v) v.playbackRate = Math.min(2.0, v.playbackRate + 0.25); }"
        )
        speed_js = "() => { const v = document.querySelector('video'); return v ? v.playbackRate : 1; }"
        speed = await page.evaluate(speed_js)
        return {"success": True, "action": "speed_up", "speed": f"{speed}x"}

    elif action in ("speed_down", "yavasla"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); "
            "if(v) v.playbackRate = Math.max(0.25, v.playbackRate - 0.25); }"
        )
        speed_js = "() => { const v = document.querySelector('video'); return v ? v.playbackRate : 1; }"
        speed = await page.evaluate(speed_js)
        return {"success": True, "action": "speed_down", "speed": f"{speed}x"}

    elif action in ("normal_speed", "normal", "hiz_sifirla"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.playbackRate = 1.0; }")
        return {"success": True, "action": "normal_speed", "speed": "1x"}

    elif action in ("pip", "picture_in_picture", "kucuk_ekran"):
        await page.evaluate(
            "() => { const v = document.querySelector('video'); "
            "if(v && v.requestPictureInPicture) v.requestPictureInPicture(); }"
        )
        return {"success": True, "action": "pip", "message": "Picture-in-Picture modu"}

    elif action in ("like", "begen"):
        like_sel = "ytd-toggle-button-renderer#segmented-like-button button, button[aria-label*='Begen']"
        like_btn = await page.query_selector(like_sel)
        if like_btn:
            await like_btn.click()
            return {"success": True, "action": "like", "message": "Video beğenildi"}
        return {"success": False, "error": "Beğen butonu bulunamadı"}

    elif action in ("subscribe", "abone", "abone_ol"):
        sub_btn = await page.query_selector("ytd-subscribe-button-renderer button, #subscribe-button button")
        if sub_btn:
            await sub_btn.click()
            return {"success": True, "action": "subscribe", "message": "Kanala abone olundu"}
        return {"success": False, "error": "Abone butonu bulunamadı"}

    return {"success": False, "error": f"Bilinmeyen video kontrolü: {action}"}


def _parse_time_to_seconds(time_str: str) -> float | None:
    """Parse time string to seconds. Supports: '1:30', '10:25', '1:30:00', '90', '1.5dakika'."""
    import re

    ts = time_str.lower().strip()

    # Try "X dakika" / "X saniye" format
    m = re.match(r"(\d+(?:\.\d+)?)\s*dakika", ts)
    if m:
        return float(m.group(1)) * 60
    m = re.match(r"(\d+(?:\.\d+)?)\s*saniye", ts)
    if m:
        return float(m.group(1))

    # Try "HH:MM:SS" or "MM:SS" or "SS" format
    parts = ts.split(":")
    if len(parts) == 3:
        try:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
    elif len(parts) == 2:
        try:
            return int(parts[0]) * 60 + float(parts[1])
        except ValueError:
            return None
    elif len(parts) == 1:
        try:
            return float(ts)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Genel Tarayici Kontrol
# ---------------------------------------------------------------------------


async def browser_action(page: Any, action: str, **kwargs: Any) -> dict[str, Any]:
    """General browser page actions beyond YouTube.

    Actions: scroll_up, scroll_down, go_back, go_forward, refresh,
             get_url, get_title, wait, close_tab, new_tab, switch_tab,
             select, hover, focus
    """
    action = action.lower().strip()

    if action in ("scroll_up", "yukari_kaydir"):
        delta = kwargs.get("delta", 500)
        await page.mouse.wheel(0, -delta)
        return {"success": True, "action": "scroll_up", "delta": delta}

    elif action in ("scroll_down", "asagi_kaydir"):
        delta = kwargs.get("delta", 500)
        await page.mouse.wheel(0, delta)
        return {"success": True, "action": "scroll_down", "delta": delta}

    elif action in ("go_back", "geri"):
        await page.go_back()
        return {"success": True, "action": "go_back", "url": page.url}

    elif action in ("go_forward", "ileri"):
        await page.go_forward()
        return {"success": True, "action": "go_forward", "url": page.url}

    elif action in ("refresh", "yenile", "yeniden_yukle"):
        await page.reload()
        return {"success": True, "action": "refresh", "url": page.url}

    elif action in ("get_url", "url"):
        return {"success": True, "action": "get_url", "url": page.url}

    elif action in ("get_title", "baslik"):
        title = await page.title()
        return {"success": True, "action": "get_title", "title": title}

    elif action in ("wait", "bekle"):
        seconds = kwargs.get("seconds", 2)
        await asyncio.sleep(seconds)
        return {"success": True, "action": "wait", "seconds": seconds}

    elif action in ("new_tab", "yeni_sekme"):
        new_page = await page.context.new_page()
        url = kwargs.get("url", "about:blank")
        if url and url != "about:blank":
            await new_page.goto(url, timeout=30000)
        return {"success": True, "action": "new_tab", "url": new_page.url}

    elif action in ("close_tab", "sekme_kapat"):
        await page.close()
        return {"success": True, "action": "close_tab"}

    elif action in ("select", "sec"):
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        if selector and value:
            await page.select_option(selector, value)
            return {"success": True, "action": "select", "selector": selector}
        return {"success": False, "error": "selector ve value gerekli"}

    elif action in ("hover", "ustune_gel"):
        selector = kwargs.get("selector", "")
        if selector:
            await page.hover(selector)
            return {"success": True, "action": "hover", "selector": selector}
        return {"success": False, "error": "selector gerekli"}

    elif action in ("focus", "odaklan"):
        selector = kwargs.get("selector", "")
        if selector:
            await page.focus(selector)
            return {"success": True, "action": "focus", "selector": selector}
        return {"success": False, "error": "selector gerekli"}

    return {"success": False, "error": f"Bilinmeyen tarayici eylemi: {action}"}
