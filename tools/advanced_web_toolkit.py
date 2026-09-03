"""Advanced Web Toolkit — link extraction and article parsing."""

from __future__ import annotations

from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class WebExtractAllLinks(BaseTool):
    name = "web_extract_all_links"
    description = "Extract all hyperlinks from a URL. Uses Playwright for JS-rendered pages."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = tool_input.parameters.get("url", "")
        if not url:
            return self._failure("url is required")

        # Try Playwright first (renders JS)
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    html = await page.content()
                finally:
                    await browser.close()

            soup = BeautifulSoup(html, "html.parser")
            links = []
            for a in soup.find_all("a", href=True):
                href = a.get("href")
                if not href:
                    continue
                links.append({
                    "text": (a.get_text() or "").strip(),
                    "url": urljoin(url, str(href)),
                })
            return self._success(
                f"Extracted {len(links)} links (Playwright)",
                data={"url": url, "links": links, "method": "playwright"},
            )
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback: httpx
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
                links.append({
                    "text": (a.get_text() or "").strip(),
                    "url": urljoin(url, str(href)),
                })
            return self._success(
                f"Extracted {len(links)} links (httpx)",
                data={"url": url, "links": links, "method": "httpx"},
            )
        except Exception as exc:
            return self._failure(f"Failed to extract links: {exc}")
        except Exception as exc:
            return self._failure(str(exc))


class WebReadMainArticle(BaseTool):
    name = "web_read_main_article"
    description = "Extract the main article text from a URL. Uses Playwright for JS-rendered pages."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = tool_input.parameters.get("url", "")
        if not url:
            return self._failure("url is required")

        # Try Playwright first
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    html = await page.content()
                finally:
                    await browser.close()

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
                tag.decompose()
            article = soup.find("article")
            text = article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)
            max_chars = tool_input.parameters.get("max_chars", 15_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return self._success(
                "Article extracted (Playwright)",
                data={"url": url, "text": text, "method": "playwright"},
            )
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback: httpx
        try:
            async with httpx.AsyncClient(timeout=20, verify=False) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
                tag.decompose()
            article = soup.find("article")
            text = article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)
            max_chars = tool_input.parameters.get("max_chars", 15_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return self._success(
                "Article extracted (httpx)",
                data={"url": url, "text": text, "method": "httpx"},
            )
        except Exception as exc:
            return self._failure(f"Failed to extract article: {exc}")
        except Exception as exc:
            return self._failure(str(exc))
