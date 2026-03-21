"""Web Research Toolkit — multi-page scraping with depth control."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


class WebDeepCrawl(BaseTool):
    name = "web_deep_crawl"
    description = "Crawl a site up to a limited depth and return page texts."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        start_url = str(self._first_param(params, "url", "start_url", default="")).strip()
        max_pages = int(self._first_param(params, "max_pages", default=20) or 20)
        max_pages = max(1, min(max_pages, 200))
        max_chars_per_page = int(
            self._first_param(params, "max_chars_per_page", default=10000) or 10000
        )
        max_chars_per_page = max(1000, min(max_chars_per_page, 50000))
        scroll_steps = int(self._first_param(params, "scroll_steps", default=14) or 14)
        scroll_steps = max(0, min(scroll_steps, 200))
        scroll_delay_ms = int(self._first_param(params, "scroll_delay_ms", default=120) or 120)
        scroll_delay_ms = max(10, min(scroll_delay_ms, 2000))
        include_subdomains = bool(self._first_param(params, "include_subdomains", default=False))
        save_to_desktop = bool(self._first_param(params, "save_to_desktop", default=False))
        output_path_raw = str(self._first_param(params, "output_path", "path", default="")).strip()

        if not start_url:
            return self._failure("url is required")
        if not start_url.startswith("http"):
            start_url = "https://" + start_url

        try:
            visited: set[str] = set()
            to_visit = [start_url]
            results: list[dict[str, str]] = []
            base_host = urlparse(start_url).netloc
            browser_mode = False
            pw: Any | None = None
            browser = None
            context = None
            page = None

            try:
                from playwright.async_api import async_playwright  # type: ignore[import-not-found]

                pw = await async_playwright().start()
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(ignore_https_errors=True)
                page = await context.new_page()
                browser_mode = True
            except Exception:
                browser_mode = False

            async with httpx.AsyncClient(timeout=25) as client:
                while to_visit and len(results) < max_pages:
                    raw_url = to_visit.pop(0)
                    url = _normalize_url(raw_url)
                    if not url or url in visited:
                        continue
                    visited.add(url)

                    html = ""
                    title = ""
                    text = ""

                    if browser_mode and page is not None:
                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=35_000)
                            for _ in range(scroll_steps):
                                await page.mouse.wheel(0, 1400)
                                await page.wait_for_timeout(scroll_delay_ms)
                            html = await page.content()
                            title = await page.title()
                            text = await page.evaluate(
                                """
                                () => {
                                    const scripts = document.querySelectorAll(
                                      'script, style, noscript'
                                    );
                                    scripts.forEach(s => s.remove());
                                    return document.body ? document.body.innerText : '';
                                }
                                """
                            )
                        except Exception:
                            continue
                    else:
                        try:
                            r = await client.get(url)
                            r.raise_for_status()
                            html = r.text
                        except Exception:
                            continue

                    if not html and not text:
                        continue

                    if not text:
                        soup_fallback = BeautifulSoup(html, "html.parser")
                        text = soup_fallback.get_text("\n", strip=True)

                    if len(text) > max_chars_per_page:
                        text = text[:max_chars_per_page] + "\n... (truncated)"

                    soup = (
                        BeautifulSoup(html, "html.parser")
                        if html
                        else BeautifulSoup("", "html.parser")
                    )
                    if not title:
                        title = (
                            soup.title.string.strip() if soup.title and soup.title.string else ""
                        )

                    results.append(
                        {
                            "url": url,
                            "title": title,
                            "text": text,
                        }
                    )

                    for a in soup.find_all("a", href=True):
                        href_raw = a.get("href")
                        if not isinstance(href_raw, str):
                            continue
                        href = _normalize_url(urljoin(url, href_raw))
                        if not href:
                            continue
                        if _is_internal_link(href, base_host, include_subdomains):
                            if href not in visited:
                                to_visit.append(href)

            summary_md = _build_markdown_summary(start_url, results)

            output_path: str | None = None
            if save_to_desktop and not output_path_raw:
                slug = _slugify_host(base_host) or "site"
                output_path = f"Desktop/{slug}_deep_crawl.md"
            elif output_path_raw:
                output_path = output_path_raw

            saved_path = ""
            if output_path:
                target, _ = resolve_user_path(output_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(summary_md, encoding="utf-8")
                saved_path = str(target)

            if page is not None:
                await page.close()
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()
            if pw is not None:
                await pw.stop()

            return self._success(
                "Deep crawl completed",
                data={
                    "start_url": start_url,
                    "count": len(results),
                    "pages": results,
                    "summary_markdown": summary_md,
                    "saved_path": saved_path,
                    "browser_mode": browser_mode,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return ""
    cleaned = parsed._replace(fragment="")
    return cleaned.geturl()


def _is_internal_link(url: str, base_host: str, include_subdomains: bool) -> bool:
    host = urlparse(url).netloc.lower()
    base = (base_host or "").lower()
    if not host or not base:
        return False
    if host == base:
        return True
    return include_subdomains and host.endswith("." + base)


def _build_markdown_summary(start_url: str, pages: list[dict[str, str]]) -> str:
    lines = [
        "# Web Deep Crawl Ozeti",
        "",
        f"- Baslangic URL: {start_url}",
        f"- Ziyaret edilen sayfa: {len(pages)}",
        "",
    ]

    for i, page in enumerate(pages, start=1):
        title = page.get("title") or "(baslik yok)"
        url = page.get("url") or ""
        text = page.get("text") or ""
        lines.extend(
            [
                f"## {i}. {title}",
                "",
                f"URL: {url}",
                "",
                text,
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _slugify_host(host: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", host).strip("_")
