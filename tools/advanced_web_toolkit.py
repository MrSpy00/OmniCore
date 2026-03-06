"""Advanced Web Toolkit — link extraction and article parsing."""

from __future__ import annotations

from urllib.parse import urljoin
from typing import Any

import httpx
from bs4 import BeautifulSoup

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class WebExtractAllLinks(BaseTool):
    name = "web_extract_all_links"
    description = "Extract all hyperlinks from a URL."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = tool_input.parameters.get("url", "")
        if not url:
            return self._failure("url is required")

        try:
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text

            soup = BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a.get("href")
                if not href:
                    continue
                links.append(
                    {
                        "text": (a.get_text() or "").strip(),
                        "url": urljoin(url, str(href)),  # type: ignore[arg-type]
                    }
                )
            return self._success(
                f"Extracted {len(links)} links",
                data={"url": url, "links": links},
            )
        except Exception as exc:
            return self._failure(str(exc))


class WebReadMainArticle(BaseTool):
    name = "web_read_main_article"
    description = "Extract the main article text from a URL."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = tool_input.parameters.get("url", "")
        if not url:
            return self._failure("url is required")

        try:
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text

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

            return self._success(
                "Article extracted",
                data={"url": url, "content": text},
            )
        except Exception as exc:
            return self._failure(str(exc))
