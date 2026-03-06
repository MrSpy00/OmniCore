"""OCR Toolkit — extract text from images."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path

import easyocr

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


class OcrReadImage(BaseTool):
    name = "ocr_read_image"
    description = "Extract text from an image file in the sandbox."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path = str(
            self._first_param(params, "path", "file_path", "image_path", "value", default="")
        )
        if not path:
            return self._failure("path is required")

        try:
            target = _resolve_sandboxed(path)
            text = await asyncio.to_thread(_run_ocr, target)
            return self._success("OCR completed", data={"text": text})
        except Exception as exc:
            return self._failure(str(exc))


def _run_ocr(path: Path) -> str:
    reader = _get_reader()
    result = reader.readtext(str(path), detail=0, paragraph=True)
    return "\n".join(str(line) for line in result)


@lru_cache(maxsize=1)
def _get_reader() -> easyocr.Reader:
    return easyocr.Reader(["en", "tr"], gpu=False)
