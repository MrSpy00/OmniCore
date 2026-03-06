"""Deep web and OSINT toolkit."""

from __future__ import annotations

import asyncio
import re
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import cast

import dns.resolver
import httpx
from bs4 import BeautifulSoup

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.base import resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


class WebBypassScraper(BaseTool):
    name = "web_bypass_scraper"
    description = "Fetch HTML using browser-like headers to bypass simple blocks."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default=""))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
        try:
            async with httpx.AsyncClient(
                timeout=20, headers=headers, follow_redirects=True, verify=False
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
            html = response.text
            return self._success("HTML fetched", data={"url": url, "html": html[:20000]})
        except Exception as exc:
            return self._failure(str(exc))


class WebExtractAllEmails(BaseTool):
    name = "web_extract_all_emails"
    description = "Extract all public email addresses from a web page."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default=""))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
                response = await client.get(url)
                response.raise_for_status()
            emails = sorted(
                set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", response.text))
            )
            return self._success("Email extraction completed", data={"url": url, "emails": emails})
        except Exception as exc:
            return self._failure(str(exc))


class WebDownloadAllImages(BaseTool):
    name = "web_download_all_images"
    description = "Download all images from a page to the host OS."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default=""))
        output_dir = str(self._first_param(params, "output_dir", default="downloaded_images"))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            saved = await _download_images(url, _resolve_sandboxed(output_dir))
            return self._success("Images downloaded", data={"count": len(saved), "files": saved})
        except Exception as exc:
            return self._failure(str(exc))


class OsintDnsLookup(BaseTool):
    name = "osint_dns_lookup"
    description = "Get A, MX, TXT, and CNAME DNS records for a domain."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        domain = str(self._first_param(params, "domain", "host", "query", default=""))
        if not domain:
            return self._failure("domain is required")
        try:
            records = await asyncio.to_thread(_dns_lookup, domain)
            return self._success(
                "DNS lookup completed", data={"domain": domain, "records": records}
            )
        except Exception as exc:
            return self._failure(str(exc))


async def _download_images(url: str, output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, verify=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        base_url = str(url)
        image_urls: list[str] = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            src_str = str(src)
            image_urls.append(urljoin(base_url, src_str))  # type: ignore[arg-type]
        saved: list[str] = []
        for index, image_url in enumerate(image_urls, start=1):
            try:
                image_response = await client.get(image_url)
                image_response.raise_for_status()
                suffix = Path(urlparse(image_url).path).suffix or ".img"
                target = output_dir / f"image_{index}{suffix}"
                await asyncio.to_thread(target.write_bytes, image_response.content)
                saved.append(str(target))
            except Exception:
                continue
        return saved


def _dns_lookup(domain: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"A": [], "MX": [], "TXT": [], "CNAME": []}
    record_types = ["A", "MX", "TXT", "CNAME"]
    for record_type in record_types:
        try:
            answers = dns.resolver.resolve(domain, record_type)
            result[record_type] = [str(answer).strip() for answer in answers]
        except Exception:
            result[record_type] = []
    return result
