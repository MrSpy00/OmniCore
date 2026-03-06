"""Singularity toolkit with extra autonomous capabilities."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

import cv2
import feedparser
import httpx
import pandas as pd
import pygetwindow as gw
from PIL import Image, ImageOps, ImageStat  # type: ignore[import-not-found]
from win10toast import ToastNotifier

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


def _resolve_sandboxed(path_str: str) -> Path:
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


class ImgReadQrCode(BaseTool):
    name = "img_read_qr_code"
    description = "Read QR codes from an image using OpenCV."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        path = str(self._first_param(self._params(tool_input), "path", "image_path", default=""))
        if not path:
            return self._failure("path is required")
        try:
            data = await asyncio.to_thread(_read_qr, _resolve_sandboxed(path))
            return self._success("QR scan completed", data={"codes": data})
        except Exception as exc:
            return self._failure(str(exc))


class WebFetchRssFeed(BaseTool):
    name = "web_fetch_rss_feed"
    description = "Fetch and summarize an RSS/Atom feed."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = str(self._first_param(self._params(tool_input), "url", default=""))
        if not url:
            return self._failure("url is required")
        try:
            feed = await asyncio.to_thread(feedparser.parse, url)
            entries = [
                {"title": e.get("title", ""), "link": e.get("link", "")} for e in feed.entries[:10]
            ]
            return self._success(
                "RSS feed fetched", data={"title": feed.feed.get("title", ""), "entries": entries}
            )
        except Exception as exc:
            return self._failure(str(exc))


class WebFetchHackerNewsTop(BaseTool):
    name = "web_fetch_hackernews_top"
    description = "Fetch top Hacker News stories."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                ids = (
                    await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                ).json()[:10]
                stories = []
                for story_id in ids:
                    item = (
                        await client.get(
                            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                        )
                    ).json()
                    stories.append({"title": item.get("title", ""), "url": item.get("url", "")})
            return self._success("Hacker News fetched", data={"stories": stories})
        except Exception as exc:
            return self._failure(str(exc))


class DocPdfToTextAdvanced(BaseTool):
    name = "doc_pdf_to_text_advanced"
    description = "Convert a PDF to text using page-aware extraction."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from PyPDF2 import PdfReader

        path = str(self._first_param(self._params(tool_input), "path", default=""))
        if not path:
            return self._failure("path is required")
        try:
            text = await asyncio.to_thread(_pdf_to_text, _resolve_sandboxed(path))
            return self._success("PDF converted to text", data={"text": text[:30000]})
        except Exception as exc:
            return self._failure(str(exc))


class WebPageToPdfReport(BaseTool):
    name = "web_page_to_pdf_report"
    description = "Render a webpage to PDF using Playwright."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from tools.web_toolkit import _get_browser

        params = self._params(tool_input)
        url = str(self._first_param(params, "url", default=""))
        output_path = str(self._first_param(params, "output_path", default="page_report.pdf"))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            target = _resolve_sandboxed(output_path)
            context = await _get_browser()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.pdf(path=str(target), print_background=True)
            finally:
                await page.close()
            return self._success("Webpage PDF created", data={"path": str(target)})
        except Exception as exc:
            return self._failure(str(exc))


class SysHardwareSerials(BaseTool):
    name = "sys_hardware_serials"
    description = "Extract motherboard, BIOS, and disk serial numbers."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            data = await asyncio.to_thread(_hardware_serials)
            return self._success("Hardware serials fetched", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class DesktopSendNotification(BaseTool):
    name = "desktop_send_notification"
    description = "Send a native Windows desktop notification."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        title = str(self._first_param(params, "title", default="OmniCore"))
        message = str(self._first_param(params, "message", "text", default=""))
        if not message:
            return self._failure("message is required")
        try:
            await asyncio.to_thread(
                ToastNotifier().show_toast, title, message, duration=5, threaded=False
            )
            return self._success(
                "Desktop notification sent", data={"title": title, "message": message}
            )
        except Exception as exc:
            return self._failure(str(exc))


class OsTrackActiveWindow(BaseTool):
    name = "os_track_active_window"
    description = "Report the currently active foreground window title."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            title = await asyncio.to_thread(lambda: gw.getActiveWindowTitle() or "")
            return self._success("Active window fetched", data={"title": title})
        except Exception as exc:
            return self._failure(str(exc))


class ClipboardTransformText(BaseTool):
    name = "clipboard_transform_text"
    description = "Transform clipboard text to upper/lower/title case."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        import pyperclip

        mode = str(self._first_param(self._params(tool_input), "mode", default="upper")).lower()
        try:
            text = await asyncio.to_thread(pyperclip.paste)
            if mode == "lower":
                transformed = text.lower()
            elif mode == "title":
                transformed = text.title()
            else:
                transformed = text.upper()
            await asyncio.to_thread(pyperclip.copy, transformed)
            return self._success("Clipboard transformed", data={"text": transformed})
        except Exception as exc:
            return self._failure(str(exc))


class DataMergeJson(BaseTool):
    name = "data_merge_json"
    description = "Merge multiple JSON files into a single JSON array or object list."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        files = params.get("files", [])
        output_path = str(self._first_param(params, "output_path", default="merged.json"))
        if not isinstance(files, list) or not files:
            return self._failure("files list is required")
        try:
            merged = await asyncio.to_thread(
                _merge_json_files, [_resolve_sandboxed(str(f)) for f in files]
            )
            target = _resolve_sandboxed(output_path)
            await asyncio.to_thread(
                target.write_text,
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return self._success(
                "JSON files merged", data={"path": str(target), "items": len(merged)}
            )
        except Exception as exc:
            return self._failure(str(exc))


class WebExtractTables(BaseTool):
    name = "web_extract_tables"
    description = "Extract HTML tables from a webpage into JSON rows."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = str(self._first_param(self._params(tool_input), "url", default=""))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            tables = await asyncio.to_thread(pd.read_html, url)
            data = [table.fillna("").to_dict(orient="records") for table in tables]
            return self._success(
                "Web tables extracted", data={"table_count": len(data), "tables": data}
            )
        except Exception as exc:
            return self._failure(str(exc))


class SysEnvironmentSnapshot(BaseTool):
    name = "sys_environment_snapshot"
    description = "Capture current environment variables and key system paths."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        env = dict(os.environ)
        sample = {k: env[k] for k in sorted(env)[:50]}
        return self._success("Environment snapshot captured", data={"environment": sample})


class FileWatchDirectory(BaseTool):
    name = "file_watch_directory"
    description = "Snapshot a directory state and write a hash report."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        root = _resolve_sandboxed(str(self._first_param(params, "root", "path", default=".")))
        output_path = _resolve_sandboxed(
            str(self._first_param(params, "output_path", default="watch_snapshot.json"))
        )
        try:
            snapshot = await asyncio.to_thread(_snapshot_dir, root)
            await asyncio.to_thread(
                output_path.write_text, json.dumps(snapshot, indent=2), encoding="utf-8"
            )
            return self._success(
                "Directory snapshot captured",
                data={"path": str(output_path), "entries": len(snapshot)},
            )
        except Exception as exc:
            return self._failure(str(exc))


class MediaContactSheet(BaseTool):
    name = "media_contact_sheet"
    description = "Build a contact sheet from images in a folder."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        root = _resolve_sandboxed(str(self._first_param(params, "root", "path", default=".")))
        output_path = _resolve_sandboxed(
            str(self._first_param(params, "output_path", default="contact_sheet.jpg"))
        )
        try:
            await asyncio.to_thread(_make_contact_sheet, root, output_path)
            return self._success("Contact sheet created", data={"path": str(output_path)})
        except Exception as exc:
            return self._failure(str(exc))


class NetHttpProbe(BaseTool):
    name = "net_http_probe"
    description = "Probe an HTTP endpoint and return status, timing, and headers."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        url = str(self._first_param(self._params(tool_input), "url", default=""))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(url)
            return self._success(
                "HTTP probe completed",
                data={
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "url": str(response.url),
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


def _read_qr(path: Path) -> list[str]:
    image = cv2.imread(str(path))
    detector = cv2.QRCodeDetector()
    found, decoded_info, _, _ = detector.detectAndDecodeMulti(image)
    if found:
        return [text for text in decoded_info if text]
    single, _, _ = detector.detectAndDecode(image)
    return [single] if single else []


def _pdf_to_text(path: Path) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _hardware_serials() -> dict[str, str]:
    commands = {
        "bios_serial": ["wmic", "bios", "get", "serialnumber"],
        "baseboard_serial": ["wmic", "baseboard", "get", "serialnumber"],
        "disk_serial": ["wmic", "diskdrive", "get", "serialnumber"],
    }
    result: dict[str, str] = {}
    for key, cmd in commands.items():
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        result[key] = " | ".join(lines[1:]) if len(lines) > 1 else ""
    return result


def _merge_json_files(paths: list[Path]) -> list[object]:
    merged: list[object] = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            merged.extend(data)
        else:
            merged.append(data)
    return merged


def _snapshot_dir(root: Path) -> list[dict[str, str | int]]:
    result: list[dict[str, str | int]] = []
    for item in root.rglob("*"):
        if item.is_file():
            result.append(
                {
                    "path": str(item),
                    "size": item.stat().st_size,
                    "sha256": hashlib.sha256(item.read_bytes()).hexdigest(),
                }
            )
    return result


def _make_contact_sheet(root: Path, output: Path) -> None:
    images = [Image.open(path).convert("RGB") for path in sorted(root.glob("*")) if path.is_file()]
    if not images:
        raise ValueError("No images found")
    thumbs = [ImageOps.fit(img, (200, 200)) for img in images[:16]]
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 200, rows * 200), "black")
    for idx, thumb in enumerate(thumbs):
        x = (idx % cols) * 200
        y = (idx // cols) * 200
        sheet.paste(thumb, (x, y))
    sheet.save(output)
