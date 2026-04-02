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
        crawl_opts = _parse_crawl_options(self, params)
        start_url = crawl_opts["start_url"]
        if not start_url:
            return self._failure("url is required")

        try:
            crawl_data = await _run_deep_crawl(crawl_opts)
            results = crawl_data["results"]
            browser_mode = crawl_data["browser_mode"]
            base_host = crawl_data["base_host"]

            summary_md = _build_markdown_summary(start_url, results)

            output_path: str | None = None
            output_path_raw = str(crawl_opts["output_path_raw"])
            if crawl_opts["save_to_desktop"] and not output_path_raw:
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


def _parse_crawl_options(tool: WebDeepCrawl, params: dict[str, Any]) -> dict[str, Any]:
    start_url = str(tool._first_param(params, "url", "start_url", default="")).strip()
    if start_url and not start_url.startswith("http"):
        start_url = "https://" + start_url

    max_pages = int(tool._first_param(params, "max_pages", default=20) or 20)
    max_chars_per_page = int(
        tool._first_param(params, "max_chars_per_page", default=10000) or 10000
    )
    scroll_steps = int(tool._first_param(params, "scroll_steps", default=14) or 14)
    scroll_delay_ms = int(tool._first_param(params, "scroll_delay_ms", default=120) or 120)

    return {
        "start_url": start_url,
        "max_pages": max(1, min(max_pages, 200)),
        "max_chars_per_page": max(1000, min(max_chars_per_page, 50000)),
        "scroll_steps": max(0, min(scroll_steps, 200)),
        "scroll_delay_ms": max(10, min(scroll_delay_ms, 2000)),
        "include_subdomains": bool(tool._first_param(params, "include_subdomains", default=False)),
        "save_to_desktop": bool(tool._first_param(params, "save_to_desktop", default=False)),
        "output_path_raw": str(
            tool._first_param(params, "output_path", "path", default="")
        ).strip(),
    }


async def _run_deep_crawl(opts: dict[str, Any]) -> dict[str, Any]:
    start_url = str(opts["start_url"])
    visited: set[str] = set()
    to_visit = [start_url]
    results: list[dict[str, str]] = []
    base_host = urlparse(start_url).netloc

    browser_mode, pw, browser, context, page = await _init_playwright_page()
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            while to_visit and len(results) < int(opts["max_pages"]):
                raw_url = to_visit.pop(0)
                url = _normalize_url(raw_url)
                if not url or url in visited:
                    continue
                visited.add(url)

                page_data = await _fetch_page_data(url, page, client, opts)
                if page_data is None:
                    continue

                html = page_data["html"]
                title = page_data["title"]
                text = page_data["text"]

                if not html and not text:
                    continue

                prepared = _prepare_page_payload(
                    url, html, title, text, int(opts["max_chars_per_page"])
                )
                results.append({"url": url, "title": prepared["title"], "text": prepared["text"]})

                for href in _extract_internal_links(
                    url,
                    html,
                    base_host,
                    bool(opts["include_subdomains"]),
                ):
                    if href not in visited:
                        to_visit.append(href)
    finally:
        await _close_playwright(pw, browser, context, page)

    return {
        "results": results,
        "browser_mode": browser_mode,
        "base_host": base_host,
    }


async def _init_playwright_page():
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
    return browser_mode, pw, browser, context, page


async def _close_playwright(pw, browser, context, page) -> None:
    if page is not None:
        await page.close()
    if context is not None:
        await context.close()
    if browser is not None:
        await browser.close()
    if pw is not None:
        await pw.stop()


async def _fetch_page_data(url: str, page, client: httpx.AsyncClient, opts: dict[str, Any]):
    if page is not None:
        return await _fetch_with_browser(
            url, page, int(opts["scroll_steps"]), int(opts["scroll_delay_ms"])
        )
    return await _fetch_with_http(url, client)


async def _fetch_with_browser(url: str, page, scroll_steps: int, scroll_delay_ms: int):
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
                const scripts = document.querySelectorAll('script, style, noscript');
                scripts.forEach(s => s.remove());
                return document.body ? document.body.innerText : '';
            }
            """
        )
        return {"html": html, "title": title, "text": text}
    except Exception:
        return None


async def _fetch_with_http(url: str, client: httpx.AsyncClient):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return {"html": response.text, "title": "", "text": ""}
    except Exception:
        return None


def _prepare_page_payload(
    url: str,
    html: str,
    title: str,
    text: str,
    max_chars_per_page: int,
) -> dict[str, str]:
    normalized_text = text
    if not normalized_text:
        soup_fallback = BeautifulSoup(html, "html.parser")
        normalized_text = soup_fallback.get_text("\n", strip=True)

    if len(normalized_text) > max_chars_per_page:
        normalized_text = normalized_text[:max_chars_per_page] + "\n... (truncated)"

    soup = BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")
    normalized_title = title
    if not normalized_title:
        normalized_title = soup.title.string.strip() if soup.title and soup.title.string else ""

    return {"url": url, "title": normalized_title, "text": normalized_text}


def _extract_internal_links(
    current_url: str,
    html: str,
    base_host: str,
    include_subdomains: bool,
) -> list[str]:
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href_raw = anchor.get("href")
        if not isinstance(href_raw, str):
            continue
        href = _normalize_url(urljoin(current_url, href_raw))
        if not href:
            continue
        if _is_internal_link(href, base_host, include_subdomains):
            links.append(href)
    return links


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
