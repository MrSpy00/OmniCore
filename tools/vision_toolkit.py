"""Vision Toolkit — screen capture + OCR analysis."""

from __future__ import annotations

import asyncio
from pathlib import Path

import mss  # type: ignore[import-not-found]
import pytesseract
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


class GuiAnalyzeScreen(BaseTool):
    name = "gui_analyze_screen"
    description = "Take a screenshot and extract visible text via OCR."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        output_path = str(
            self._first_param(params, "output_path", "path", default="vision_capture.png")
        )
        region = params.get("region")
        if isinstance(region, str):
            region = None

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            await asyncio.to_thread(_capture_screen, save_path, region)
            text = await asyncio.to_thread(_ocr_image, save_path)
            max_chars = int(params.get("max_chars", 20_000))
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"

            return self._success(
                "Screen analyzed",
                data={"path": str(save_path), "text": text},
            )
        except Exception as exc:
            return self._failure(str(exc))


def _capture_screen(path: Path, region: dict | None) -> None:
    with mss.mss() as sct:
        if region:
            bbox = {
                "left": int(region.get("left", 0)),
                "top": int(region.get("top", 0)),
                "width": int(region.get("width", 0)),
                "height": int(region.get("height", 0)),
            }
        else:
            bbox = sct.monitors[0]
        shot = sct.grab(bbox)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        img.save(path)


def _ocr_image(path: Path) -> str:
    img = Image.open(path)
    return pytesseract.image_to_string(img)
