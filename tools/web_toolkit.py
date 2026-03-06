"""Web Toolkit — Playwright-based headless browser automation.

Provides tools for searching the web, navigating to URLs, extracting
page content, and taking screenshots.
"""

from __future__ import annotations

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.base import resolve_user_path

logger = get_logger(__name__)

# Shared browser instance management
_browser_context: dict = {}


async def _get_browser():
    """Lazily launch a headless Chromium browser and return a context."""
    from playwright.async_api import async_playwright

    if "playwright" not in _browser_context:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        _browser_context["playwright"] = pw
        _browser_context["browser"] = browser
        _browser_context["context"] = context
    return _browser_context["context"]


async def shutdown_browser() -> None:
    """Gracefully close the browser (call at application shutdown)."""
    if "browser" in _browser_context:
        await _browser_context["browser"].close()
    if "playwright" in _browser_context:
        await _browser_context["playwright"].stop()
    _browser_context.clear()


# ---------------------------------------------------------------------------
# Navigate to URL
# ---------------------------------------------------------------------------
class WebNavigate(BaseTool):
    name = "web_navigate"
    description = "Navigate to a URL and return the page text content."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", "query", default=""))
        if not url:
            return self._failure("No URL provided")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            context = await _get_browser()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                title = await page.title()
                content = await page.evaluate(
                    """
                    () => {
                        const scripts = document.querySelectorAll('script, style, noscript');
                        scripts.forEach(s => s.remove());
                        return document.body ? document.body.innerText : '';
                    }
                    """
                )
                max_chars = params.get("max_chars", 15_000)
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n... (truncated)"

                logger.info("web.navigate", url=url, title=title)
                return self._success(
                    f"Loaded: {title}",
                    data={"title": title, "url": url, "content": content},
                )
            finally:
                await page.close()
        except Exception as exc:
            return self._failure(f"Navigation failed: {exc}")


# ---------------------------------------------------------------------------
# Web Search
# ---------------------------------------------------------------------------
class WebSearch(BaseTool):
    name = "web_search"
    description = "Search the web using DuckDuckGo and return top results."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        query = str(self._first_param(params, "query", "q", "value", default=""))
        if not query:
            return self._failure("No search query provided")

        try:
            context = await _get_browser()
            page = await context.new_page()
            try:
                search_url = f"https://duckduckgo.com/?q={query}&ia=web"
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)

                content = await page.evaluate(
                    """
                    () => {
                        const scripts = document.querySelectorAll('script, style, noscript');
                        scripts.forEach(s => s.remove());
                        return document.body ? document.body.innerText : '';
                    }
                    """
                )
                max_chars = params.get("max_chars", 12_000)
                if len(content) > max_chars:
                    content = content[:max_chars] + "\n... (truncated)"

                logger.info("web.search", query=query)
                return self._success(
                    f"Search page loaded for '{query}'",
                    data={"query": query, "content": content},
                )
            finally:
                await page.close()
        except Exception as exc:
            return self._failure(f"Search failed: {exc}")


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------
class WebScreenshot(BaseTool):
    name = "web_screenshot"
    description = "Take a screenshot of a web page and save it to the host OS."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default=""))
        output_path = str(
            self._first_param(params, "output_path", "path", "file_path", default="screenshot.png")
        )
        if not url:
            return self._failure("No URL provided")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            save_path, _ = resolve_user_path(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            context = await _get_browser()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.screenshot(path=str(save_path), full_page=False)
                logger.info("web.screenshot", url=url, path=str(save_path))
                return self._success(
                    f"Screenshot saved to {save_path.name}",
                    data={"path": str(save_path)},
                )
            finally:
                await page.close()
        except Exception as exc:
            return self._failure(f"Screenshot failed: {exc}")
