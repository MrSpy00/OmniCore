"""Browser Automation Toolkit — Headless web fetching and page rendering."""

from __future__ import annotations

import asyncio
import urllib.request

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class BrowserFetchPage(BaseTool):
    """Fetch web page HTML and extract clean text content."""

    name = "browser_fetch_page"
    description = (
        "Fetch web page URL content and extract clean readable text. "
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

        try:
            html_text = await asyncio.to_thread(_fetch_url_html, url)
            clean_text = _extract_clean_text_from_html(html_text)
            return self._success(
                f"Web page fetched successfully from {url}.",
                data={"url": url, "text": clean_text[:4000], "length": len(clean_text)},
            )
        except Exception as exc:
            return self._failure(f"Failed to fetch web page: {exc}")


class BrowserTakeScreenshot(BaseTool):
    """Capture a screenshot of a target desktop window or region."""

    name = "browser_take_screenshot"
    description = (
        "Capture a visual screenshot of the current screen or web browser window. "
        "Parameters: save_path (optional target PNG file path)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        save_path = str(self._first_param(params, "save_path", "path", default="") or "").strip()

        from tools.computer_use_toolkit import ScreenCapture

        sub_input = ToolInput(
            tool_name="screen_capture",
            parameters={"output_path": save_path} if save_path else {},
        )
        return await ScreenCapture().execute(sub_input)


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
