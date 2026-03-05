"""Advanced Web Toolkit — link extraction and article scraping."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.web_toolkit import _get_browser

logger = get_logger(__name__)


class WebExtractLinks(BaseTool):
    name = "web_extract_links"
    description = "Extract all hyperlinks from a web page."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = tool_input.parameters.get("url", "")
        if not url:
            return self._failure("No URL provided")

        try:
            context = await _get_browser()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                html = await page.content()
            finally:
                await page.close()

            soup = BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a.get("href")
                if not href:
                    continue
                links.append(
                    {
                        "text": (a.get_text() or "").strip(),
                        "url": urljoin(url, href),
                    }
                )

            max_links = int(tool_input.parameters.get("max_links", 200))
            links = links[:max_links]
            logger.info("web.extract_links", url=url, count=len(links))
            return self._success(
                f"Extracted {len(links)} links",
                data={"url": url, "links": links},
            )
        except Exception as exc:
            return self._failure(f"Link extraction failed: {exc}")


class WebReadArticle(BaseTool):
    name = "web_read_article"
    description = "Extract the main article text from a web page."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = tool_input.parameters.get("url", "")
        if not url:
            return self._failure("No URL provided")

        try:
            context = await _get_browser()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                html = await page.content()
            finally:
                await page.close()

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
                tag.decompose()

            article = soup.find("article")
            if article:
                text = article.get_text("\n", strip=True)
            else:
                text = soup.get_text("\n", strip=True)

            max_chars = tool_input.parameters.get("max_chars", 15_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"

            logger.info("web.read_article", url=url)
            return self._success(
                "Article extracted",
                data={"url": url, "content": text},
            )
        except Exception as exc:
            return self._failure(f"Article extraction failed: {exc}")
