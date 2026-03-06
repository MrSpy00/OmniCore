"""Advanced GUI/computer-use tools."""

from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path
from typing import Any, cast

import imageio.v2 as imageio
import mss  # type: ignore[import-not-found]
import pyautogui
from PIL import Image  # type: ignore[import-not-found]

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.vision_toolkit import REGION_TEXT_PROMPT, analyze_image_with_gemini


def _resolve_sandboxed(path_str: str) -> Path:
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


class GuiClickImageOnScreen(BaseTool):
    name = "gui_click_image_on_screen"
    description = "Find an image on screen and click it."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        image_path = str(self._first_param(params, "image_path", "path", default=""))
        confidence = float(self._first_param(params, "confidence", default=0.8) or 0.8)
        if not image_path:
            return self._failure("image_path is required")
        try:
            target = _resolve_sandboxed(image_path)
            point = await asyncio.to_thread(
                pyautogui.locateCenterOnScreen, str(target), confidence=confidence
            )
            if point is None:
                return self._failure("Image not found on screen")
            await asyncio.to_thread(pyautogui.click, point.x, point.y)
            return self._success("Image found and clicked", data={"x": point.x, "y": point.y})
        except Exception as exc:
            return self._failure(str(exc))


class GuiDragAndDrop(BaseTool):
    name = "gui_drag_and_drop"
    description = "Drag the mouse from point A to point B."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        x1 = int(self._first_param(params, "x1", "start_x", default=0) or 0)
        y1 = int(self._first_param(params, "y1", "start_y", default=0) or 0)
        x2 = int(self._first_param(params, "x2", "end_x", default=0) or 0)
        y2 = int(self._first_param(params, "y2", "end_y", default=0) or 0)
        duration = float(self._first_param(params, "duration", default=0.5) or 0.5)
        try:
            await asyncio.to_thread(pyautogui.moveTo, x1, y1, duration=0.1)
            await asyncio.to_thread(pyautogui.dragTo, x2, y2, duration=duration, button="left")
            return self._success("Drag-and-drop completed", data={"from": [x1, y1], "to": [x2, y2]})
        except Exception as exc:
            return self._failure(str(exc))


class GuiHumanType(BaseTool):
    name = "gui_human_type"
    description = "Type text with variable human-like delays."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        text = str(self._first_param(params, "text", "content", "value", default=""))
        if not text:
            return self._failure("text is required")
        try:
            await asyncio.to_thread(_human_type, text)
            return self._success("Human-like typing completed", data={"length": len(text)})
        except Exception as exc:
            return self._failure(str(exc))


class GuiRecordScreen(BaseTool):
    name = "gui_record_screen"
    description = "Record the screen for N seconds and save as MP4."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        seconds = float(self._first_param(params, "seconds", "duration", default=5) or 5)
        fps = int(self._first_param(params, "fps", default=5) or 5)
        output_path = str(
            self._first_param(params, "output_path", "path", default="screen_record.mp4")
        )
        try:
            save_path = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_record_screen, save_path, seconds, fps)
            return self._success("Screen recording saved", data={"path": str(save_path)})
        except Exception as exc:
            return self._failure(str(exc))


class GuiExtractTextFromRegion(BaseTool):
    name = "gui_extract_text_from_region"
    description = "Capture a screen region and extract text using Gemini vision."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        region = {
            "left": int(self._first_param(params, "left", default=0) or 0),
            "top": int(self._first_param(params, "top", default=0) or 0),
            "width": int(self._first_param(params, "width", default=0) or 0),
            "height": int(self._first_param(params, "height", default=0) or 0),
        }
        output_path = str(
            self._first_param(params, "output_path", "path", default="region_ocr.png")
        )
        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_capture_region, save_path, region)
            text = await asyncio.to_thread(analyze_image_with_gemini, save_path, REGION_TEXT_PROMPT)
            max_chars = int(self._first_param(params, "max_chars", default=20_000) or 20_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return self._success(
                "Region analysis completed", data={"path": str(save_path), "text": text}
            )
        except Exception as exc:
            return self._failure(str(exc))


def _human_type(text: str) -> None:
    for char in text:
        pyautogui.write(char)
        time.sleep(random.uniform(0.03, 0.12))


def _record_screen(path: Path, seconds: float, fps: int) -> None:
    frames = []
    frame_count = max(1, int(seconds * fps))
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        for _ in range(frame_count):
            shot = sct.grab(monitor)
            frames.append(Image.frombytes("RGB", shot.size, shot.rgb))
            time.sleep(1 / max(1, fps))
    with imageio.get_writer(path, fps=fps) as writer:
        append_data = cast(Any, writer).append_data
        for frame in frames:
            append_data(frame)


def _capture_region(path: Path, region: dict[str, int]) -> None:
    if region["width"] <= 0 or region["height"] <= 0:
        raise ValueError("width and height must be greater than zero")
    with mss.mss() as sct:
        shot = sct.grab(region)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        image.save(path)
