"""Browser Automation Toolkit — Headless web fetching and page rendering."""

from __future__ import annotations

import asyncio
import urllib.request

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class BrowserFetchPage(BaseTool):
    """Fetch web page content — Playwright for JS-rendered pages, urllib fallback."""

    name = "browser_fetch_page"
    description = (
        "Fetch web page content with full JavaScript rendering via Playwright. "
        "Falls back to urllib for simple pages. "
        "Parameters: url (http/https web URL)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "link", default="") or "").strip()

        if not url:
            return self._failure("url parameter is required.")

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Try Playwright first (renders JavaScript)
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    text = await page.inner_text("body")
                    clean = text[:8000] if text else ""
                    return self._success(
                        f"Web page fetched (Playwright) from {url}.",
                        data={"url": url, "text": clean, "length": len(clean), "method": "playwright"},
                    )
                finally:
                    await browser.close()
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback: urllib (static HTTP)
        try:
            html_text = await asyncio.to_thread(_fetch_url_html, url)
            clean_text = _extract_clean_text_from_html(html_text)
            return self._success(
                f"Web page fetched (urllib) from {url}.",
                data={"url": url, "text": clean_text[:4000], "length": len(clean_text), "method": "urllib"},
            )
        except Exception as exc:
            return self._failure(f"Failed to fetch web page: {exc}")


class BrowserTakeScreenshot(BaseTool):
    """Capture a screenshot of a target desktop window or region."""

    name = "browser_take_screenshot"
    description = (
        "Capture a visual screenshot of the current screen or web browser window. "
        "Parameters: save_path (optional target PNG file path, defaults to Desktop/screenshot.png)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        save_path = str(self._first_param(params, "save_path", "output_path", "path", default="") or "").strip()

        from tools.gui_automation_toolkit import GuiTakeScreenshot

        sub_input = ToolInput(
            tool_name="gui_take_screenshot",
            parameters={"output_path": save_path or "Desktop/screenshot.png"},
        )
        return await GuiTakeScreenshot().execute(sub_input)


class BrowserLaunch(BaseTool):
    """Launch a real desktop browser (Chrome, Edge, Brave, or system default) visibly."""

    name = "browser_launch"
    description = (
        "Launch a visible browser process on the host OS. "
        "Parameters: url (optional URL or search term to open), browser (optional: chrome|edge|brave|default)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", "query", default="https://www.google.com") or "").strip()
        browser_choice = str(self._first_param(params, "browser", "app", default="default") or "default").lower()

        if not url:
            url = "https://www.google.com"
        elif not url.startswith(("http://", "https://")):
            if "." in url and " " not in url:
                url = f"https://{url}"
            else:
                import urllib.parse

                url = f"https://www.google.com/search?q={urllib.parse.quote(url)}"

        launched = await asyncio.to_thread(_launch_browser_process, url, browser_choice)
        if launched.get("success"):
            return self._success(
                f"Browser launched visibly with URL: {url}",
                data={"url": url, **launched},
            )
        return self._failure(f"Failed to launch browser: {launched.get('error')}")


def _launch_browser_process(url: str, browser_name: str = "default") -> dict:
    import os
    import subprocess
    import sys

    from tools.base import force_window_foreground

    if sys.platform != "win32":
        import webbrowser

        webbrowser.open_new(url)
        return {"success": True, "method": "webbrowser.open_new"}

    # Common Windows executable paths
    chrome_paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    brave_paths = [
        os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.expandvars(r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]

    exe_path = None
    if browser_name in ("chrome", "google-chrome"):
        exe_path = next((p for p in chrome_paths if os.path.exists(p)), None)
    elif browser_name in ("edge", "msedge"):
        exe_path = next((p for p in edge_paths if os.path.exists(p)), None)
    elif browser_name == "brave":
        exe_path = next((p for p in brave_paths if os.path.exists(p)), None)

    # Fallback to any installed modern browser if default
    if not exe_path and browser_name == "default":
        for candidate in chrome_paths + edge_paths + brave_paths:
            if os.path.exists(candidate):
                exe_path = candidate
                break

    try:
        if exe_path and os.path.exists(exe_path):
            proc = subprocess.Popen([exe_path, url], close_fds=True)
            import time

            time.sleep(1.0)
            for title in ("Chrome", "Edge", "Brave", "Browser"):
                force_window_foreground(title, timeout_seconds=1.5)
            return {"success": True, "method": "subprocess", "exe": exe_path, "pid": proc.pid}

        # OS default shell open fallback
        os.startfile(url)
        import time

        time.sleep(1.0)
        for title in ("Chrome", "Edge", "Brave", "Browser"):
            force_window_foreground(title, timeout_seconds=1.5)
        return {"success": True, "method": "os.startfile"}
    except Exception as exc:
        try:
            import webbrowser

            webbrowser.open_new(url)
            return {"success": True, "method": "webbrowser_fallback"}
        except Exception as fallback_exc:
            return {"success": False, "error": f"{exc} (fallback: {fallback_exc})"}


def _fetch_url_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OmniCore/0.40.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _extract_clean_text_from_html(html: str) -> str:
    import re

    # Strip script and style tags
    clean = re.sub(r"<(script|style).*?>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Strip HTML tags
    clean = re.sub(r"<.*?>", " ", clean)
    # Normalize whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


class BrowserPlaywrightInteract(BaseTool):
    """Real browser automation via Playwright using user's default browser."""

    name = "browser_interact"
    description = (
        "Interact with web pages using user's default browser. "
        "Actions: navigate, click, fill, scroll, screenshot, get_text, "
        "youtube_search, open_and_play, wait_for, scroll_up, scroll_down, "
        "go_back, go_forward, refresh, get_url, get_title, new_tab, "
        "select, hover, focus. "
        "Parameters: url, action, selector, value, save_path, timeout, delta."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default="") or "").strip()
        action = str(self._first_param(params, "action", default="navigate") or "navigate").lower()
        selector = str(self._first_param(params, "selector", "css", "xpath", default="") or "")
        value = str(self._first_param(params, "value", "text", default="") or "")
        save_path = str(self._first_param(params, "save_path", "path", default="Desktop/browser_screenshot.png") or "")
        timeout = int(params.get("timeout", 30000))

        try:
            from tools.browser_helpers import (
                browser_action,
                launch_user_browser,
                smart_youtube_play,
            )
        except ImportError:
            return self._failure("browser_helpers modulu bulunamadi")

        # General browser actions (don't need URL)
        general_actions = (
            "scroll_up",
            "scroll_down",
            "go_back",
            "go_forward",
            "refresh",
            "get_url",
            "get_title",
            "new_tab",
            "close_tab",
            "select",
            "hover",
            "focus",
            "wait",
        )
        if action in general_actions:
            try:
                pw, browser, page = await launch_user_browser(headless=False)
                try:
                    result = await browser_action(
                        page,
                        action,
                        selector=selector,
                        value=value,
                        delta=int(value) if value.isdigit() else 500,
                        seconds=int(value) if value.isdigit() else 2,
                        url=url,
                    )
                    if result.get("success"):
                        return self._success(
                            result.get("message", action),
                            data=result,
                        )
                    return self._failure(result.get("error", "Hata"))
                finally:
                    pass
            except Exception as exc:
                return self._failure(f"Tarayici hatasi: {exc}")

        try:
            pw, browser, page = await launch_user_browser(headless=False)
            try:
                if action == "youtube_search" and value:
                    result = await smart_youtube_play(page, value)
                    if result.get("success"):
                        return self._success(
                            f"YouTube video: '{result['title']}'",
                            data=result,
                        )
                    return self._failure(result.get("error", "YouTube hatasi"))

                if action == "open_and_play" and value:
                    result = await smart_youtube_play(page, value)
                    if result.get("success"):
                        return self._success(
                            f"YouTube baslatildi: '{result['title']}'",
                            data=result,
                        )
                    return self._failure(result.get("error", "YouTube hatasi"))

                if url:
                    await page.goto(url, timeout=timeout)

                if action == "navigate":
                    return self._success(f"Sayfaya gidildi: {page.url}", data={"url": page.url})
                elif action == "click" and selector:
                    await page.click(selector, timeout=timeout)
                    return self._success(f"Tiklandi: {selector}")
                elif action == "fill" and selector:
                    await page.fill(selector, value, timeout=timeout)
                    return self._success(f"Dolduruldu: {selector}")
                elif action == "scroll":
                    delta = int(value or "500")
                    await page.mouse.wheel(0, delta)
                    return self._success(f"Kaydirildi: {delta}px")
                elif action == "screenshot":
                    await page.screenshot(path=save_path, full_page=False)
                    return self._success(f"Ekran goruntusu: {save_path}")
                elif action == "get_text":
                    text = await page.inner_text("body")
                    return self._success(text[:4000], data={"url": page.url, "text": text[:4000]})
                elif action == "wait_for" and selector:
                    await page.wait_for_selector(selector, timeout=timeout)
                    return self._success(f"Element bulundu: {selector}")
                else:
                    actions_list = (
                        "navigate, click, fill, scroll, screenshot, get_text, "
                        "youtube_search, open_and_play, wait_for, scroll_up, "
                        "scroll_down, go_back, go_forward, refresh, get_url, "
                        "get_title, new_tab, select, hover, focus"
                    )
                    return self._failure(f"Bilinmeyen action: {action}. Kullanilabilir: {actions_list}")
            finally:
                pass
        except Exception as exc:
            return self._failure(f"Tarayici hatasi: {exc}")

    async def _youtube_search(self, page, query: str) -> ToolOutput:
        """Search YouTube, find first video result, return URL."""
        import urllib.parse

        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        await page.goto(search_url, timeout=30000)
        await page.wait_for_selector("ytd-video-renderer", timeout=15000)
        first_video = await page.query_selector("ytd-video-renderer a#video-title")
        if first_video:
            href = await first_video.get_attribute("href")
            title = await first_video.inner_text()
            video_url = f"https://www.youtube.com{href}"
            return self._success(
                f"YouTube arama sonucu: '{title}'",
                data={"url": video_url, "title": title, "search_query": query},
            )
        return self._failure(f"YouTube'da '{query}' icin sonuc bulunamadi")

    async def _youtube_open_and_play(self, page, query: str) -> ToolOutput:
        """Search YouTube, navigate to first video, and play it."""
        import urllib.parse

        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        await page.goto(search_url, timeout=30000)
        await page.wait_for_selector("ytd-video-renderer", timeout=15000)
        first_video = await page.query_selector("ytd-video-renderer a#video-title")
        if first_video:
            href = await first_video.get_attribute("href")
            title = await first_video.inner_text()
            video_url = f"https://www.youtube.com{href}"
            await page.goto(video_url, timeout=30000)
            # Try to click play button if video doesn't auto-play
            try:
                play_btn = await page.query_selector("button.ytp-large-play-button")
                if play_btn:
                    await play_btn.click()
            except Exception:
                pass
            return self._success(
                f"YouTube video baslatildi: '{title}'",
                data={"url": video_url, "title": title, "status": "playing"},
            )
        return self._failure(f"YouTube'da '{query}' icin video bulunamadi")
