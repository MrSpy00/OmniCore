"""OCR Toolkit — extract text from images."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytesseract
from PIL import Image

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
        path = tool_input.parameters.get("path", "")
        if not path:
            return self._failure("path is required")

        try:
            target = _resolve_sandboxed(path)
            text = await asyncio.to_thread(_run_ocr, target)
            return self._success("OCR completed", data={"text": text})
        except Exception as exc:
            return self._failure(str(exc))


def _run_ocr(path: Path) -> str:
    image = Image.open(path)
    return pytesseract.image_to_string(image)
