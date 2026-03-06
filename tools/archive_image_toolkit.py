"""Archive and image metadata toolkit."""

from __future__ import annotations

import asyncio
import shutil
import zipfile
from pathlib import Path

from PIL import Image  # type: ignore[import-not-found]

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


class ArchiveCreateZip(BaseTool):
    name = "archive_create_zip"
    description = "Create a ZIP archive from a file or directory in the sandbox."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        source = str(self._first_param(params, "source", "path", default=""))
        output_path = str(self._first_param(params, "output_path", default="archive.zip"))
        if not source:
            return self._failure("source is required")
        try:
            src = _resolve_sandboxed(source)
            dest = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_make_zip, src, dest)
            return self._success("ZIP archive created", data={"path": str(dest)})
        except Exception as exc:
            return self._failure(str(exc))


class ArchiveExtractZip(BaseTool):
    name = "archive_extract_zip"
    description = "Extract a ZIP archive into the sandbox."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        archive_path = str(self._first_param(params, "archive_path", "path", default=""))
        destination = str(self._first_param(params, "destination", default="."))
        if not archive_path:
            return self._failure("archive_path is required")
        try:
            src = _resolve_sandboxed(archive_path)
            dest = _resolve_sandboxed(destination)
            await asyncio.to_thread(_extract_zip, src, dest)
            return self._success("ZIP archive extracted", data={"path": str(dest)})
        except Exception as exc:
            return self._failure(str(exc))


class ImageReadExif(BaseTool):
    name = "image_read_exif"
    description = "Read EXIF metadata from an image in the sandbox."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path = str(self._first_param(params, "path", "image_path", default=""))
        if not path:
            return self._failure("path is required")
        try:
            image_path = _resolve_sandboxed(path)
            exif = await asyncio.to_thread(_read_exif, image_path)
            return self._success("EXIF metadata read", data={"exif": exif})
        except Exception as exc:
            return self._failure(str(exc))


def _make_zip(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as archive:
        if src.is_dir():
            for item in src.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(src))
        else:
            archive.write(src, src.name)


def _extract_zip(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "r") as archive:
        archive.extractall(dest)


def _read_exif(path: Path) -> dict[str, str]:
    image = Image.open(path)
    raw = image.getexif()
    return {str(key): str(value) for key, value in raw.items()}
