"""Shared Playwright browser launcher — uses user's default browser with persistent session."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    import winreg

from config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BrowserInfo:
    """Detected user browser information."""

    name: str
    engine: str  # "chromium", "firefox", "webkit"
    channel: str | None  # Only valid Playwright channels: "chrome", "msedge", etc.
    executable_path: str | None


# Windows registry handler -> Browser configuration mapping
_HANDLER_TO_BROWSER: dict[str, tuple[str, str, str | None]] = {
    # ProgId: (name, engine, playwright_channel)
    "ChromeHTML": ("chrome", "chromium", "chrome"),
    "ChromeSSOHTM": ("chrome", "chromium", "chrome"),
    "MSEdgeHTM": ("edge", "chromium", "msedge"),
    "MSEdgeHTML": ("edge", "chromium", "msedge"),
    "BraveHTML": ("brave", "chromium", None),
    "BraveSSOHTM": ("brave", "chromium", None),
    "ChromiumHTM": ("chromium", "chromium", None),
    "FirefoxURL": ("firefox", "firefox", None),
    "FirefoxHTML": ("firefox", "firefox", None),
    "TorBrowserURL": ("tor", "firefox", None),
    "LibreWolfHTML": ("librewolf", "firefox", None),
    "ZenHTML": ("zen", "firefox", None),
    "VivaldiHTML": ("vivaldi", "chromium", None),
    "OperaHTML": ("opera", "chromium", None),
    "Safari": ("safari", "webkit", None),
}

# Browser executable paths fallback
_BROWSER_PATHS: list[tuple[str, str, str | None, list[str], int]] = [
    # (name, engine, channel, [paths], priority)
    (
        "brave",
        "chromium",
        None,
        [
            r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        1,
    ),
    (
        "chrome",
        "chromium",
        "chrome",
        [
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
        ],
        2,
    ),
    (
        "edge",
        "chromium",
        "msedge",
        [
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
        ],
        3,
    ),
    (
        "firefox",
        "firefox",
        None,
        [
            r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
            r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
        ],
        4,
    ),
    (
        "librewolf",
        "firefox",
        None,
        [
            r"%ProgramFiles%\LibreWolf\librewolf.exe",
            r"%LocalAppData%\LibreWolf\librewolf.exe",
        ],
        5,
    ),
    (
        "tor",
        "firefox",
        None,
        [
            r"%ProgramFiles%\Tor Browser\Browser\firefox.exe",
            r"%LocalAppData%\Tor Browser\Browser\firefox.exe",
        ],
        6,
    ),
    (
        "zen",
        "firefox",
        None,
        [
            r"%ProgramFiles%\Zen Browser\zen.exe",
            r"%LocalAppData%\Zen Browser\zen.exe",
        ],
        7,
    ),
    (
        "vivaldi",
        "chromium",
        None,
        [
            r"%LocalAppData%\Vivaldi\Application\vivaldi.exe",
            r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe",
        ],
        8,
    ),
    (
        "opera",
        "chromium",
        None,
        [
            r"%ProgramFiles%\Opera\opera.exe",
            r"%LocalAppData%\Opera Software\Opera Stable\opera.exe",
        ],
        9,
    ),
    (
        "chromium",
        "chromium",
        None,
        [
            r"%LocalAppData%\Chromium\Application\chrome.exe",
        ],
        10,
    ),
]


def _find_exe_in_paths(paths: list[str]) -> str | None:
    """Find the first existing executable in the given list of path templates."""
    for p in paths:
        expanded = os.path.expandvars(p)
        if os.path.exists(expanded):
            return expanded
    return None


def _detect_user_browser() -> BrowserInfo:
    """Detect the user's default browser and return BrowserInfo with engine and executable.

    Detection order:
    0. Persona preferred browser (if explicitly chosen or learned with high confidence)
    1. Windows registry (default HTTP handler)
    2. File system scan for installed browsers
    3. Fallback to default Playwright chromium
    """
    try:
        from config.persona_system import get_persona_manager

        persona = get_persona_manager()
        pref = (persona.get_preference("preferred_browser") or "").strip().lower()
        if pref and pref != "auto":
            for b_name, b_engine, b_channel, paths, _prio in _BROWSER_PATHS:
                if b_name == pref:
                    exe = _find_exe_in_paths(paths)
                    if exe:
                        return BrowserInfo(name=b_name, engine=b_engine, channel=b_channel, executable_path=exe)
    except Exception:
        pass

    if sys.platform == "win32":
        return _detect_browser_windows()
    elif sys.platform == "darwin":
        return _detect_browser_macos()
    return BrowserInfo(name="chromium", engine="chromium", channel=None, executable_path=None)


def _detect_browser_windows() -> BrowserInfo:
    """Detect default browser on Windows via registry + file scan."""
    # Method 1: Registry — default HTTP handler
    try:
        key_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            prog_id, _ = winreg.QueryValueEx(key, "ProgId")
            prog_str = str(prog_id)
            if prog_str in _HANDLER_TO_BROWSER:
                name, engine, channel = _HANDLER_TO_BROWSER[prog_str]

                # Find executable path for this browser
                exe_path = None
                for b_name, _b_engine, _b_channel, paths, _prio in _BROWSER_PATHS:
                    if b_name == name:
                        exe_path = _find_exe_in_paths(paths)
                        break

                # Also try App Paths registry
                if not exe_path:
                    try:
                        app_key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe"
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, app_key) as akey:
                            val, _ = winreg.QueryValueEx(akey, "")
                            if os.path.exists(str(val)):
                                exe_path = str(val)
                    except (OSError, FileNotFoundError):
                        pass

                logger.info(
                    "browser.detected_registry",
                    prog_id=prog_str,
                    name=name,
                    engine=engine,
                    channel=channel,
                    exe_path=exe_path,
                )
                try:
                    from config.persona_system import get_persona_manager

                    get_persona_manager().learn_from_interaction(
                        "browser",
                        name,
                        confidence=0.85,
                        context="windows_registry_detection",
                    )
                except Exception:
                    pass
                return BrowserInfo(name=name, engine=engine, channel=channel, executable_path=exe_path)
    except (OSError, FileNotFoundError):
        pass

    # Method 2: File system scan — find installed browser by priority
    for name, engine, channel, paths, _priority in sorted(_BROWSER_PATHS, key=lambda x: x[4]):
        exe = _find_exe_in_paths(paths)
        if exe:
            logger.info("browser.detected_filesystem", name=name, path=exe, engine=engine)
            return BrowserInfo(name=name, engine=engine, channel=channel, executable_path=exe)

    return BrowserInfo(name="chromium", engine="chromium", channel=None, executable_path=None)


def _detect_browser_macos() -> BrowserInfo:
    """Detect default browser on macOS."""
    try:
        import subprocess

        default_app = subprocess.run(
            ["defaults", "read", "com.apple.LaunchServices/com.apple.launchservices.secure", "LSHandlers"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = default_app.stdout.lower()
        if "brave" in output:
            return BrowserInfo(name="brave", engine="chromium", channel=None, executable_path=None)
        if "chrome" in output:
            return BrowserInfo(name="chrome", engine="chromium", channel="chrome", executable_path=None)
        if "firefox" in output:
            return BrowserInfo(name="firefox", engine="firefox", channel=None, executable_path=None)
        if "safari" in output:
            return BrowserInfo(name="safari", engine="webkit", channel=None, executable_path=None)
    except Exception:
        pass
    return BrowserInfo(name="chromium", engine="chromium", channel=None, executable_path=None)


# ---------------------------------------------------------------------------
# Singleton Global Browser Session Manager
# ---------------------------------------------------------------------------


class _GlobalBrowserSession:
    """Thread-safe, resilient singleton browser session manager.

    Maintains a single persistent browser instance and context across all tool calls,
    preventing duplicate windows, preserving logins/cookies, and handling crashes cleanly.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._active_page: Any = None
        self._is_persistent_context: bool = False
        self._profile_dir: Path = Path.home() / ".omnicore" / "browser_profile"

    def _ensure_profile_dir(self) -> str:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        return str(self._profile_dir)

    def is_alive(self) -> bool:
        """Check if browser session is active and responsive."""
        if not self._context:
            return False
        if self._browser and hasattr(self._browser, "is_connected"):
            if not self._browser.is_connected():
                return False
        try:
            # If pages list is accessible without exception, context is alive
            _ = self._context.pages
            return True
        except Exception:
            return False

    async def get_or_create_session(self, headless: bool = False) -> tuple[Any, Any, Any]:
        """Return (playwright, browser_or_context, context).

        Re-uses existing session if available; launches new one only when needed.
        """
        async with self._lock:
            if self.is_alive():
                return self._pw, (self._browser or self._context), self._context

            # Reset any stale references
            await self._cleanup_internal()

            from playwright.async_api import async_playwright

            self._pw = await async_playwright().start()
            b_info = _detect_user_browser()
            user_data_dir = self._ensure_profile_dir()

            logger.info(
                "browser.session_creating",
                name=b_info.name,
                engine=b_info.engine,
                channel=b_info.channel,
                exe=b_info.executable_path,
                headless=headless,
            )

            # --- Multi-tier resilient launch strategy ---
            # Tier 1: Try attaching to existing CDP session (if user started browser with remote debugging)
            if b_info.engine == "chromium":
                try:
                    browser = await self._pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=1500)
                    if browser and browser.contexts:
                        self._browser = browser
                        self._context = browser.contexts[0]
                        self._is_persistent_context = False
                        logger.info("browser.session_attached_cdp")
                        return self._pw, self._browser, self._context
                except Exception:
                    pass

            # Tier 2: Persistent context with user's detected browser executable or channel
            # Uses dedicated OmniCore profile directory to avoid lock conflicts with running user browsers
            common_args = [
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ]
            if not headless:
                common_args.append("--start-maximized")

            # Try persistent context launch
            try:
                if b_info.engine == "firefox":
                    exe = (
                        b_info.executable_path
                        if b_info.executable_path and os.path.exists(b_info.executable_path)
                        else None
                    )
                    context = await self._pw.firefox.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        headless=headless,
                        executable_path=exe,
                        viewport=None if not headless else {"width": 1280, "height": 800},
                        ignore_https_errors=True,
                    )
                elif b_info.engine == "webkit":
                    context = await self._pw.webkit.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        headless=headless,
                        viewport=None if not headless else {"width": 1280, "height": 800},
                        ignore_https_errors=True,
                    )
                else:  # Chromium-based (Chrome, Edge, Brave, Vivaldi, Opera)
                    launch_kwargs: dict[str, Any] = {
                        "user_data_dir": user_data_dir,
                        "headless": headless,
                        "args": common_args,
                        "viewport": None if not headless else {"width": 1280, "height": 800},
                        "ignore_https_errors": True,
                    }
                    if b_info.executable_path and os.path.exists(b_info.executable_path):
                        launch_kwargs["executable_path"] = b_info.executable_path
                    elif b_info.channel:
                        launch_kwargs["channel"] = b_info.channel

                    context = await self._pw.chromium.launch_persistent_context(**launch_kwargs)

                self._context = context
                self._browser = context
                self._is_persistent_context = True
                logger.info("browser.persistent_session_ready", engine=b_info.engine, name=b_info.name)
                return self._pw, self._browser, self._context
            except Exception as exc:
                logger.warning("browser.persistent_launch_failed_fallback_standard", error=str(exc))

            # Tier 3: Standard launch fallback (if persistent context has file lock or profile issue)
            try:
                engine_obj = getattr(self._pw, b_info.engine, self._pw.chromium)
                std_kwargs: dict[str, Any] = {"headless": headless}
                if b_info.executable_path and os.path.exists(b_info.executable_path):
                    std_kwargs["executable_path"] = b_info.executable_path
                elif b_info.channel and b_info.engine == "chromium":
                    std_kwargs["channel"] = b_info.channel

                browser = await engine_obj.launch(**std_kwargs)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800} if headless else None,
                    ignore_https_errors=True,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                )
                self._browser = browser
                self._context = context
                self._is_persistent_context = False
                logger.info("browser.standard_session_ready")
                return self._pw, self._browser, self._context
            except Exception as std_exc:
                logger.warning("browser.standard_launch_failed_fallback_chromium", error=str(std_exc))

            # Tier 4: Guaranteed fallback to bundled Chromium
            browser = await self._pw.chromium.launch(headless=headless)
            context = await browser.new_context(ignore_https_errors=True)
            self._browser = browser
            self._context = context
            self._is_persistent_context = False
            return self._pw, self._browser, self._context

    async def get_or_create_page(
        self,
        url_pattern: str | None = None,
        new_tab: bool = False,
        headless: bool = False,
    ) -> Any:
        """Get an existing page matching url_pattern, or active page, or create a new tab.

        Never opens a separate browser window; reuses the existing persistent window.
        """
        await self.get_or_create_session(headless=headless)

        # Look into existing pages in the context
        pages = [p for p in self._context.pages if not p.is_closed()]

        if not new_tab and pages:
            if url_pattern:
                for p in pages:
                    try:
                        if url_pattern.lower() in p.url.lower():
                            await p.bring_to_front()
                            self._active_page = p
                            return p
                    except Exception:
                        pass

            # If active page is still open and no pattern matched, bring active page to front
            if self._active_page and not self._active_page.is_closed():
                try:
                    await self._active_page.bring_to_front()
                    return self._active_page
                except Exception:
                    pass

            # Otherwise return the last opened page
            target_page = pages[-1]
            try:
                await target_page.bring_to_front()
                self._active_page = target_page
                return target_page
            except Exception:
                pass

        # Create a new tab in the same browser window
        new_page = await self._context.new_page()
        self._active_page = new_page
        return new_page

    async def _cleanup_internal(self) -> None:
        """Internal cleanup without locking."""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser and self._browser != self._context:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None

        self._active_page = None

    async def shutdown(self) -> None:
        """Gracefully shut down the browser session."""
        async with self._lock:
            await self._cleanup_internal()
            logger.info("browser.session_shutdown_complete")


# Global singleton instance
_GLOBAL_SESSION = _GlobalBrowserSession()


async def get_browser_session() -> _GlobalBrowserSession:
    """Access the global singleton browser session manager."""
    return _GLOBAL_SESSION


async def launch_user_browser(headless: bool = False) -> tuple[Any, Any, Any]:
    """Launch or re-use the user's default browser via Playwright.

    Returns (playwright, browser, page) tuple.
    Preserves singleton semantics so repeated calls reuse the existing window.
    """
    session = await get_browser_session()
    pw, browser, _context = await session.get_or_create_session(headless=headless)
    page = await session.get_or_create_page(headless=headless)
    return pw, browser, page


# ---------------------------------------------------------------------------
# YouTube Akıllı Atlatıcı, Bildirim ve Metadata Fonksiyonları
# ---------------------------------------------------------------------------


async def _smart_skip_youtube_ad(page: Any) -> bool:
    """Detect and skip YouTube ads, overlays, and YouTube Premium modals automatically.

    Handles:
    - YouTube Premium upsell modals ('Hayır teşekkürler', 'Dismiss', 'Not now')
    - Cookie/consent popups
    - Video pre-roll and mid-roll ads (skip button, countdown, auto-fast-forward)
    - Banner/overlay ads
    """
    skipped_anything = False

    # 1. Dismiss any YouTube Premium or promotion popups immediately
    modal_dismiss_selectors = [
        "ytd-popup-container yt-button-renderer#dismiss-button button",
        "ytd-popup-container #dismiss-button",
        "tp-yt-paper-dialog #dismiss-button",
        "ytd-mealbar-promo-renderer #dismiss-button",
        "ytd-enforcement-message-view-model button",
        "yt-button-shape button[aria-label*='Hayır']",
        "yt-button-shape button[aria-label*='Dismiss']",
        "yt-button-shape button[aria-label*='Kapat']",
        "yt-button-shape button[aria-label*='Close']",
        "button[aria-label*='Hayır']",
        "button[aria-label*='Dismiss']",
        "button[aria-label*='Şimdi değil']",
        "button[aria-label*='Not now']",
        "button[aria-label*='Kapat']",
        "button[aria-label*='Close']",
        "yt-button-renderer:has-text('Hayır teşekkürler') button",
        "yt-button-renderer:has-text('Dismiss') button",
        "yt-button-renderer:has-text('Not now') button",
        "yt-button-renderer:has-text('Şimdi değil') button",
        "button:has-text('Hayır teşekkürler')",
        "button:has-text('Şimdi değil')",
        "button:has-text('Tümünü kabul et')",
        "button:has-text('Accept all')",
    ]

    for sel in modal_dismiss_selectors:
        try:
            dismiss_btn = await page.query_selector(sel)
            if dismiss_btn and await dismiss_btn.is_visible():
                await dismiss_btn.click()
                logger.info("youtube.modal_dismissed", selector=sel)
                skipped_anything = True
                await asyncio.sleep(0.3)
                break
        except Exception:
            pass

    # 2. Check for active video ads
    for _ in range(12):  # Check periodically for up to 6 seconds
        try:
            ad_showing = await page.evaluate(
                """() => {
                    const adEl = document.querySelector('.ad-showing, .ytp-ad-player-overlay, .video-ads');
                    return !!adEl;
                }"""
            )

            if not ad_showing:
                # No ad showing currently
                break

            # Try skip button
            skip_selectors = [
                ".ytp-skip-ad-button",
                "button.ytp-ad-skip-button",
                ".ytp-ad-skip-button-modern",
                "button.ytp-ad-skip-button-slot",
                ".ytp-ad-skip-button-container button",
                "button:has-text('Atla')",
                "button:has-text('Skip')",
                "button:has-text('Skip Ad')",
            ]
            for s_sel in skip_selectors:
                skip_btn = await page.query_selector(s_sel)
                if skip_btn and await skip_btn.is_visible():
                    await skip_btn.click()
                    logger.info("youtube.ad_skipped", selector=s_sel)
                    skipped_anything = True
                    await asyncio.sleep(0.5)
                    return True

            # If ad is unskippable or has countdown, fast-forward ad video
            await page.evaluate(
                """() => {
                    const adShowing = document.querySelector('.ad-showing');
                    if (adShowing) {
                        const video = document.querySelector('video');
                        if (video) {
                            video.muted = true;
                            if (isFinite(video.duration) && video.duration > 0) {
                                video.currentTime = video.duration;
                            } else {
                                video.playbackRate = 16.0;
                            }
                        }
                    }
                }"""
            )
            skipped_anything = True

            # Close overlay ads if present
            overlay_close = await page.query_selector(".ytp-ad-overlay-close-button")
            if overlay_close and await overlay_close.is_visible():
                await overlay_close.click()
                logger.info("youtube.overlay_ad_closed")

        except Exception:
            pass
        await asyncio.sleep(0.5)

    # Ensure main video is unmuted and playing at normal rate if ad was manipulated
    try:
        await page.evaluate(
            """() => {
                const video = document.querySelector('video');
                if (video && !document.querySelector('.ad-showing')) {
                    if (video.playbackRate > 2.0) {
                        video.playbackRate = 1.0;
                    }
                }
            }"""
        )
    except Exception:
        pass

    return skipped_anything


def _parse_relative_date_to_days(text: str) -> float | None:
    """Parse relative date string into days ago.

    Supports:
    - "3 gün önce", "3 days ago" -> 3.0
    - "2 hafta önce", "2 weeks ago" -> 14.0
    - "1 ay önce", "1 month ago" -> 30.0
    - "1 yıl önce", "1 year ago" -> 365.0
    - "5 saat önce", "5 hours ago" -> 0.21
    - "30 dakika önce", "30 minutes ago" -> 0.02
    - "dün", "yesterday" -> 1.0
    - "bugün", "today" -> 0.0
    """
    if not text:
        return None

    cleaned = text.strip().lower()

    if "dün" in cleaned or "yesterday" in cleaned:
        return 1.0
    if "bugün" in cleaned or "today" in cleaned:
        return 0.0

    units = "saat|hour|hours|gün|gun|day|days|hafta|week|weeks|ay|month|months|yıl|yil|year|years|dakika|minute|minutes"
    m = re.search(rf"(\d+(?:[.,]\d+)?)\s*({units})", cleaned)
    if not m:
        return None

    value_str = m.group(1).replace(",", ".")
    unit = m.group(2)
    try:
        val = float(value_str)
    except ValueError:
        return None

    if unit in ("dakika", "minute", "minutes"):
        return round(val / (24.0 * 60.0), 3)
    if unit in ("saat", "hour", "hours"):
        return round(val / 24.0, 2)
    if unit in ("gün", "gun", "day", "days"):
        return val
    if unit in ("hafta", "week", "weeks"):
        return val * 7.0
    if unit in ("ay", "month", "months"):
        return val * 30.0
    if unit in ("yıl", "yil", "year", "years"):
        return val * 365.0

    return None


async def youtube_get_video_metadata(page: Any) -> dict[str, Any]:
    """Extract comprehensive metadata from current YouTube video page.

    Returns:
        title, channel, channel_url, upload_date, relative_date, days_ago,
        view_count, like_count, duration, current_time, is_playing.
    """
    try:
        raw = await page.evaluate(
            """() => {
                const getTxt = (sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.innerText.trim() : '';
                };

                const title = getTxt('#title h1 yt-formatted-string') ||
                              getTxt('h1.ytd-watch-metadata yt-formatted-string') ||
                              document.title.replace(' - YouTube', '').trim();

                const chSel = '#channel-name a, #owner ytd-channel-name a, #upload-info #channel-name a';
                const channelEl = document.querySelector(chSel);
                const channel = channelEl ? channelEl.innerText.trim() : '';
                const channelUrl = channelEl ? channelEl.href : '';

                const subCount = getTxt('#owner-sub-count, #upload-info #owner-sub-count');

                // Upload date text
                let dateText = getTxt('#info-strings yt-formatted-string');
                if (!dateText) {
                    const dSel = '#info-container yt-formatted-string, #description-inline-expander span';
                    const dateSpan = document.querySelector(dSel);
                    if (dateSpan) dateText = dateSpan.innerText.trim();
                }

                // View count
                let views = getTxt('#view-count, ytd-watch-metadata #info span:first-child');
                if (!views) {
                    const metaViews = document.querySelector('meta[itemprop="interactionCount"]');
                    if (metaViews) views = metaViews.getAttribute('content') || '';
                }

                // Likes
                let likes = getTxt('ytd-like-button-view-model button span, #segmented-like-button button span');

                // Video timing
                const video = document.querySelector('video');
                const duration = video ? video.duration : 0;
                const currentTime = video ? video.currentTime : 0;
                const isPaused = video ? video.paused : true;

                return {
                    title: title,
                    channel: channel,
                    channel_url: channelUrl,
                    subscriber_count: subCount,
                    date_text: dateText,
                    views: views,
                    likes: likes,
                    duration: duration,
                    current_time: currentTime,
                    is_playing: !isPaused
                };
            }"""
        )
    except Exception as exc:
        return {"success": False, "error": f"Metadata alınamadı: {exc}"}

    date_text = raw.get("date_text", "")
    days_ago = _parse_relative_date_to_days(date_text)

    # Format durations
    duration_secs = raw.get("duration", 0) or 0
    current_secs = raw.get("current_time", 0) or 0

    return {
        "success": True,
        "title": raw.get("title", ""),
        "channel": raw.get("channel", ""),
        "channel_url": raw.get("channel_url", ""),
        "subscriber_count": raw.get("subscriber_count", ""),
        "upload_date": date_text,
        "relative_date": date_text,
        "days_ago": days_ago,
        "view_count": raw.get("views", ""),
        "like_count": raw.get("likes", ""),
        "duration_seconds": round(duration_secs, 1),
        "duration_formatted": f"{int(duration_secs // 60)}:{int(duration_secs % 60):02d}",
        "current_time_formatted": f"{int(current_secs // 60)}:{int(current_secs % 60):02d}",
        "is_playing": raw.get("is_playing", False),
        "url": page.url,
    }


async def youtube_enable_notifications(page: Any) -> dict[str, Any]:
    """Enable 'All notifications' (Tüm bildirimler) for the channel on the current video or channel page."""
    # Step 1: Ensure subscribed
    try:
        sub_btn = await page.query_selector(
            "ytd-subscribe-button-renderer button:not([aria-label*='Abonelik']), #subscribe-button button"
        )
        if sub_btn:
            btn_text = (await sub_btn.inner_text()).lower()
            if "abone ol" in btn_text or "subscribe" in btn_text:
                await sub_btn.click()
                logger.info("youtube.subscribed_before_notification")
                await asyncio.sleep(1.0)
    except Exception:
        pass

    # Step 2: Find notification bell button
    bell_selectors = [
        "ytd-subscription-notification-toggle-button-renderer-next button",
        "ytd-subscribe-button-renderer yt-icon-button#notification-preference-button button",
        "#notification-preference-button button",
        "button[aria-label*='bildirim']",
        "button[aria-label*='Bildirim']",
        "button[aria-label*='notification']",
        "button[aria-label*='Notification']",
        "button[aria-label*='Zil']",
    ]

    bell_btn = None
    for sel in bell_selectors:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                bell_btn = el
                break
        except Exception:
            pass

    if not bell_btn:
        return {
            "success": False,
            "error": "Bildirim (zil) butonu bulunamadı. Oturum açıldığından veya kanala abone olunduğundan emin olun.",
        }

    try:
        await bell_btn.click()
        await asyncio.sleep(0.8)

        # Step 3: Select "All" / "Tümü" / "Tüm bildirimler" in the popup menu
        option_selectors = [
            "ytd-menu-service-item-renderer:has-text('Tümü')",
            "ytd-menu-service-item-renderer:has-text('Tüm bildirimler')",
            "ytd-menu-service-item-renderer:has-text('All')",
            "ytd-menu-service-item-renderer:has-text('All notifications')",
            "tp-yt-paper-item:has-text('Tümü')",
            "tp-yt-paper-item:has-text('All')",
            "#items > ytd-menu-service-item-renderer:first-child",
        ]

        for opt_sel in option_selectors:
            opt = await page.query_selector(opt_sel)
            if opt and await opt.is_visible():
                await opt.click()
                logger.info("youtube.all_notifications_enabled", selector=opt_sel)
                await asyncio.sleep(0.5)
                return {
                    "success": True,
                    "action": "notifications",
                    "state": "all",
                    "message": "Kanalın tüm bildirimleri başarıyla açıldı.",
                }

        return {
            "success": True,
            "action": "notifications",
            "message": "Bildirim menüsü tıklandı.",
        }
    except Exception as exc:
        return {"success": False, "error": f"Bildirimler açılırken hata oluştu: {exc}"}


async def smart_youtube_play(
    page: Any,
    query: str,
    time_str: str = "",
) -> dict[str, Any]:
    """Smart YouTube: search, find video, navigate, handle ads, play, extract metadata.

    Reuses existing tab, avoids duplicate windows, automatically dismisses popups.
    """
    # If query is direct YouTube link
    if "youtube.com/" in query or "youtu.be/" in query:
        video_url = query if query.startswith("http") else f"https://{query}"
        await page.goto(video_url, timeout=30000, wait_until="domcontentloaded")
    else:
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}"
        await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("ytd-video-renderer", timeout=15000)
        except Exception:
            pass

        # Find first video
        first_video = await page.query_selector("ytd-video-renderer a#video-title")
        if not first_video:
            return {"success": False, "error": f"'{query}' için video bulunamadı"}

        href = await first_video.get_attribute("href")
        video_url = f"https://www.youtube.com{href}"
        await page.goto(video_url, timeout=30000, wait_until="domcontentloaded")

    # Smart: wait for video player to load
    try:
        await page.wait_for_selector("video.html5-main-video, video", timeout=10000)
    except Exception:
        pass

    # Try to click play button if needed
    try:
        play_btn = await page.query_selector("button.ytp-large-play-button, button.ytp-play-button")
        if play_btn and await play_btn.is_visible():
            await asyncio.sleep(0.3)
            await play_btn.click()
    except Exception:
        pass

    # Skip ad / handle YouTube Premium popup
    await _smart_skip_youtube_ad(page)

    # If seek time specified
    seek_info = None
    if time_str:
        await asyncio.sleep(0.8)
        seek_info = await youtube_seek(page, time_str)

    # Extract metadata
    metadata = await youtube_get_video_metadata(page)

    return {
        "success": True,
        "url": video_url,
        "title": metadata.get("title", "YouTube Video"),
        "channel": metadata.get("channel", ""),
        "upload_date": metadata.get("upload_date", ""),
        "days_ago": metadata.get("days_ago"),
        "view_count": metadata.get("view_count", ""),
        "like_count": metadata.get("like_count", ""),
        "status": "playing",
        "seek": seek_info,
    }


async def smart_youtube_channel_and_play(
    page: Any,
    channel_name: str,
    enable_bell: bool = False,
) -> dict[str, Any]:
    """Navigate to YouTube channel, extract latest video with upload date, play it, and enable notifications."""
    cleaned_name = channel_name.strip()

    # Step 1: Direct @handle navigation or search
    if cleaned_name.startswith("@"):
        channel_url = f"https://www.youtube.com/{cleaned_name}/videos"
        await page.goto(channel_url, timeout=30000, wait_until="domcontentloaded")
    else:
        # Search with channel filter
        search_url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(cleaned_name)}&sp=EgIQAg%3D%3D"
        )
        await page.goto(search_url, timeout=30000, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector("ytd-channel-renderer", timeout=15000)
        except Exception:
            pass

        channel_link = await page.query_selector(
            "ytd-channel-renderer a#channel-title, ytd-channel-renderer a.yt-simple-endpoint"
        )
        if not channel_link:
            return {"success": False, "error": f"'{cleaned_name}' kanalı bulunamadı"}

        await channel_link.click()
        await page.wait_for_load_state("domcontentloaded")

    # Step 2: Navigate to 'Videos' tab (Turkish and English selectors)
    videos_tab_selectors = [
        'tp-yt-paper-tab:has-text("Videolar")',
        'tp-yt-paper-tab:has-text("Videos")',
        'yt-tab-shape:has-text("Videolar")',
        'yt-tab-shape:has-text("Videos")',
        'a[href*="/videos"]',
    ]
    for tab_sel in videos_tab_selectors:
        try:
            v_tab = await page.query_selector(tab_sel)
            if v_tab and await v_tab.is_visible():
                await v_tab.click()
                await page.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(0.5)
                break
        except Exception:
            pass

    # Optional: Enable notifications on channel page if requested
    bell_result = None
    if enable_bell:
        bell_result = await youtube_enable_notifications(page)

    # Step 3: Find the newest/latest video
    video_item_selectors = [
        "ytd-rich-item-renderer",
        "ytd-grid-video-renderer",
    ]

    first_video_elem = None
    upload_date_preview = ""

    for item_sel in video_item_selectors:
        items = await page.query_selector_all(item_sel)
        if items:
            first_video_elem = items[0]
            # Try to grab date preview (e.g. "2 gün önce", "3 hours ago")
            try:
                d_sel = "#metadata-line span:nth-child(2), .ytd-video-meta-block span:nth-child(2)"
                date_span = await first_video_elem.query_selector(d_sel)
                if date_span:
                    upload_date_preview = (await date_span.inner_text()).strip()
            except Exception:
                pass
            break

    if not first_video_elem:
        return {"success": False, "error": f"'{cleaned_name}' kanalında video bulunamadı"}

    link_el = await first_video_elem.query_selector("a#video-title-link, a#video-title")
    if not link_el:
        return {"success": False, "error": f"'{cleaned_name}' kanalının videosu tıklanamadı"}

    href = await link_el.get_attribute("href")
    title = (await link_el.inner_text()).strip()
    video_url = f"https://www.youtube.com{href}" if href.startswith("/") else href

    # Navigate to video and play in the same page
    await page.goto(video_url, timeout=30000, wait_until="domcontentloaded")

    try:
        await page.wait_for_selector("video.html5-main-video, video", timeout=10000)
    except Exception:
        pass

    try:
        play_btn = await page.query_selector("button.ytp-large-play-button")
        if play_btn and await play_btn.is_visible():
            await asyncio.sleep(0.3)
            await play_btn.click()
    except Exception:
        pass

    await _smart_skip_youtube_ad(page)

    # Extract metadata from loaded video
    metadata = await youtube_get_video_metadata(page)
    effective_upload_date = metadata.get("upload_date") or upload_date_preview
    days_ago = metadata.get("days_ago") or _parse_relative_date_to_days(upload_date_preview)

    return {
        "success": True,
        "url": video_url,
        "title": title or metadata.get("title", ""),
        "channel": cleaned_name,
        "upload_date": effective_upload_date,
        "days_ago": days_ago,
        "view_count": metadata.get("view_count", ""),
        "status": "playing",
        "notifications": bell_result,
    }


# ---------------------------------------------------------------------------
# YouTube Oynatma ve Konum Kontrolleri
# ---------------------------------------------------------------------------


def _parse_time_to_seconds(time_str: str) -> float | None:
    """Parse time string to seconds.

    Supports:
    - "1:30" -> 90.0
    - "10:25" -> 625.0
    - "1:30:00" -> 5400.0
    - "90", "90s", "90sn" -> 90.0
    - "1.5 dakika", "2 dk", "45 saniye" -> converted
    """
    ts = time_str.lower().strip()

    # "X dakika Y saniye"
    m_full = re.match(r"(\d+(?:\.\d+)?)\s*(?:dakika|dk|m)\s*(?:ve)?\s*(\d+(?:\.\d+)?)\s*(?:saniye|sn|s)?", ts)
    if m_full:
        return float(m_full.group(1)) * 60 + float(m_full.group(2))

    # "X dakika"
    m_min = re.match(r"(\d+(?:\.\d+)?)\s*(?:dakika|dk|m)$", ts)
    if m_min:
        return float(m_min.group(1)) * 60

    # "X saniye"
    m_sec = re.match(r"(\d+(?:\.\d+)?)\s*(?:saniye|sn|s)$", ts)
    if m_sec:
        return float(m_sec.group(1))

    # "HH:MM:SS" or "MM:SS" or "SS"
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


async def youtube_seek(page: Any, time_str: str) -> dict[str, Any]:
    """Seek to a specific time in a YouTube video.

    Supports exact timestamps: '1:30', '10:25', '1:30:00'
    Supports relative phrases: 'orta', 'baş', 'bas', 'son', 'çeyrek', 'ceyrek', '%50', 'yüzde 50'
    """
    # Wait for video duration to be available
    js_dur = "() => { const v = document.querySelector('video'); return v ? v.duration : 0; }"
    for _ in range(10):
        duration = await page.evaluate(js_dur)
        if duration and duration > 0:
            break
        await asyncio.sleep(0.5)

    duration = await page.evaluate(js_dur)
    if duration <= 0:
        return {"success": False, "error": "Video oynatıcı bulunamadı veya video henüz yüklenmedi"}

    ts = time_str.lower().strip()
    seconds: float | None = None

    # Handle relative positions
    if ts in ("orta", "ortaya", "ortasi", "ortası", "middle"):
        seconds = duration / 2.0
    elif ts in ("bas", "baş", "basa", "başa", "start", "beginning"):
        seconds = 0.0
    elif ts in ("son", "sona", "sonu", "end"):
        seconds = max(0.0, duration - 5.0)
    elif ts in ("ceyrek", "çeyrek", "quarter"):
        seconds = duration * 0.25
    elif "yuzde" in ts or "yüzde" in ts or "%" in ts:
        clean_num = ts.replace("yuzde", "").replace("yüzde", "").replace("%", "").strip()
        try:
            pct = float(clean_num) / 100.0
            seconds = duration * pct
        except ValueError:
            pass

    if seconds is None:
        seconds = _parse_time_to_seconds(ts)

    if seconds is None:
        return {"success": False, "error": f"Geçersiz zaman damgası: {time_str}"}

    # Clamp seconds between 0 and duration
    seconds = max(0.0, min(float(duration), float(seconds)))

    # Apply seek via video element
    await page.evaluate(
        f"""() => {{
            const v = document.querySelector('video');
            if (v) {{
                v.currentTime = {seconds};
                if (v.paused) v.play();
            }}
        }}"""
    )
    await asyncio.sleep(0.5)

    # Check for ads after seek
    await _smart_skip_youtube_ad(page)

    mins = int(seconds // 60)
    secs = int(seconds % 60)
    total_mins = int(duration // 60)
    total_secs = int(duration % 60)

    return {
        "success": True,
        "action": "seek",
        "time": f"{mins}:{secs:02d}",
        "total_duration": f"{total_mins}:{total_secs:02d}",
        "seconds": seconds,
    }


async def youtube_control(page: Any, action: str) -> dict[str, Any]:
    """Control YouTube video playback.

    action: play, pause, toggle, fullscreen, mute, unmute, volume_up,
            volume_down, next, previous, speed_up, speed_down, normal_speed,
            pip, like, subscribe, notifications
    """
    action = action.lower().strip()

    if action in ("play", "devam", "oynat", "resume"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.play(); }")
        return {"success": True, "action": "play", "message": "Video oynatılıyor"}

    elif action in ("pause", "duraklat", "dur"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.pause(); }")
        return {"success": True, "action": "pause", "message": "Video duraklatıldı"}

    elif action in ("toggle", "degistir", "değiştir", "oynatduraklat"):
        state = await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (!v) return 'bulunamadı';
                if (v.paused) {
                    v.play();
                    return 'oynatılıyor';
                } else {
                    v.pause();
                    return 'duraklatıldı';
                }
            }"""
        )
        return {"success": True, "action": "toggle", "message": f"Video {state}"}

    elif action in ("fullscreen", "tam_ekran", "ekran"):
        await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v) {
                    if (v.requestFullscreen) v.requestFullscreen();
                    else if (v.webkitRequestFullscreen) v.webkitRequestFullscreen();
                }
            }"""
        )
        return {"success": True, "action": "fullscreen", "message": "Tam ekran modu açıldı"}

    elif action in ("mute", "sessiz"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.muted = true; }")
        return {"success": True, "action": "mute", "message": "Sessize alındı"}

    elif action in ("unmute", "sesli", "ses_ac_genel"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.muted = false; }")
        return {"success": True, "action": "unmute", "message": "Ses açıldı"}

    elif action in ("volume_up", "ses_ac", "ses_artir", "ses_artır"):
        vol = await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v) {
                    v.muted = false;
                    v.volume = Math.min(1.0, v.volume + 0.1);
                    return Math.round(v.volume * 100);
                }
                return 0;
            }"""
        )
        return {"success": True, "action": "volume_up", "volume": f"%{vol}"}

    elif action in ("volume_down", "ses_kis", "ses_kıs", "ses_azalt"):
        vol = await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v) {
                    v.volume = Math.max(0.0, v.volume - 0.1);
                    return Math.round(v.volume * 100);
                }
                return 0;
            }"""
        )
        return {"success": True, "action": "volume_down", "volume": f"%{vol}"}

    elif action in ("next", "sonraki"):
        next_btn = await page.query_selector("a.ytp-next-button, button.ytp-next-button")
        if next_btn:
            await next_btn.click()
            return {"success": True, "action": "next", "message": "Sonraki videoya geçildi"}
        return {"success": False, "error": "Sonraki video butonu bulunamadı"}

    elif action in ("previous", "onceki", "önceki"):
        prev_btn = await page.query_selector("a.ytp-prev-button, button.ytp-prev-button")
        if prev_btn:
            await prev_btn.click()
            return {"success": True, "action": "previous", "message": "Önceki videoya geçildi"}
        return {"success": False, "error": "Önceki video butonu bulunamadı"}

    elif action in ("speed_up", "hizlan", "hızlan", "hiz_artir"):
        speed = await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v) {
                    v.playbackRate = Math.min(2.0, v.playbackRate + 0.25);
                    return v.playbackRate;
                }
                return 1.0;
            }"""
        )
        return {"success": True, "action": "speed_up", "speed": f"{speed}x"}

    elif action in ("speed_down", "yavasla", "yavaşla", "hiz_azalt"):
        speed = await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v) {
                    v.playbackRate = Math.max(0.25, v.playbackRate - 0.25);
                    return v.playbackRate;
                }
                return 1.0;
            }"""
        )
        return {"success": True, "action": "speed_down", "speed": f"{speed}x"}

    elif action in ("normal_speed", "normal", "hiz_sifirla", "hız_sıfırla"):
        await page.evaluate("() => { const v = document.querySelector('video'); if(v) v.playbackRate = 1.0; }")
        return {"success": True, "action": "normal_speed", "speed": "1x"}

    elif action in ("pip", "picture_in_picture", "kucuk_ekran", "küçük_ekran"):
        await page.evaluate(
            """() => {
                const v = document.querySelector('video');
                if (v && v.requestPictureInPicture) v.requestPictureInPicture();
            }"""
        )
        return {"success": True, "action": "pip", "message": "Picture-in-Picture modu etkinleştirildi"}

    elif action in ("like", "begen", "beğen"):
        like_sel = (
            "ytd-toggle-button-renderer#segmented-like-button button, "
            "button[aria-label*='Beğen'], button[aria-label*='Like']"
        )
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
        return {"success": False, "error": "Abone ol butonu bulunamadı"}

    elif action in ("notifications", "bildirim", "bildirimleri_ac", "bildirimleri_aç", "bell"):
        return await youtube_enable_notifications(page)

    return {"success": False, "error": f"Bilinmeyen video kontrol eylemi: {action}"}


# ---------------------------------------------------------------------------
# Genel Tarayıcı Eylemleri (Session Uyumlu)
# ---------------------------------------------------------------------------


async def browser_action(page: Any, action: str, **kwargs: Any) -> dict[str, Any]:
    """Execute general browser actions on page."""
    action = action.lower().strip()

    if action in ("scroll_up", "yukari_kaydir", "yukarı_kaydır"):
        delta = kwargs.get("delta", 500)
        await page.mouse.wheel(0, -delta)
        return {"success": True, "action": "scroll_up", "delta": delta}

    elif action in ("scroll_down", "asagi_kaydir", "aşağı_kaydır"):
        delta = kwargs.get("delta", 500)
        await page.mouse.wheel(0, delta)
        return {"success": True, "action": "scroll_down", "delta": delta}

    elif action in ("go_back", "geri"):
        await page.go_back()
        return {"success": True, "action": "go_back", "url": page.url}

    elif action in ("go_forward", "ileri"):
        await page.go_forward()
        return {"success": True, "action": "go_forward", "url": page.url}

    elif action in ("refresh", "yenile", "yeniden_yukle", "yeniden_yükle"):
        await page.reload()
        return {"success": True, "action": "refresh", "url": page.url}

    elif action in ("get_url", "url"):
        return {"success": True, "action": "get_url", "url": page.url}

    elif action in ("get_title", "baslik", "başlık"):
        title = await page.title()
        return {"success": True, "action": "get_title", "title": title}

    elif action in ("wait", "bekle"):
        seconds = kwargs.get("seconds", 2)
        await asyncio.sleep(seconds)
        return {"success": True, "action": "wait", "seconds": seconds}

    elif action in ("new_tab", "yeni_sekme"):
        session = await get_browser_session()
        new_page = await session.get_or_create_page(new_tab=True)
        url = kwargs.get("url", "about:blank")
        if url and url != "about:blank":
            await new_page.goto(url, timeout=30000)
        return {"success": True, "action": "new_tab", "url": new_page.url}

    elif action in ("close_tab", "sekme_kapat"):
        await page.close()
        return {"success": True, "action": "close_tab"}

    elif action in ("select", "sec", "seç"):
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        if selector and value:
            await page.select_option(selector, value)
            return {"success": True, "action": "select", "selector": selector}
        return {"success": False, "error": "selector ve value gerekli"}

    elif action in ("hover", "ustune_gel", "üstüne_gel"):
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

    return {"success": False, "error": f"Bilinmeyen tarayıcı eylemi: {action}"}
