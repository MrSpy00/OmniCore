"""Web Research Toolkit — multi-page scraping with depth control."""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class WebDeepCrawl(BaseTool):
    name = "web_deep_crawl"
    description = "Crawl a site up to a limited depth and return page texts."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        start_url = tool_input.parameters.get("url", "")
        max_pages = int(tool_input.parameters.get("max_pages", 5))
        if not start_url:
            return self._failure("url is required")

        try:
            visited = set()
            to_visit = [start_url]
            results = []
            base_host = urlparse(start_url).netloc

            async with httpx.AsyncClient(timeout=20) as client:
                while to_visit and len(results) < max_pages:
                    url = to_visit.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)
                    try:
                        r = await client.get(url)
                        r.raise_for_status()
                    except Exception:
                        continue

                    soup = BeautifulSoup(r.text, "html.parser")
                    text = soup.get_text("\n", strip=True)
                    results.append({"url": url, "text": text[:5000]})

                    for a in soup.find_all("a", href=True):
                        href = urljoin(url, a.get("href"))
                        if urlparse(href).netloc == base_host:
                            to_visit.append(href)

            return self._success("Crawl completed", data={"pages": results})
        except Exception as exc:
            return self._failure(str(exc))
