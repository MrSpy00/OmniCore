"""GUI Automation Toolkit — mouse, keyboard, and screenshots."""

from __future__ import annotations

from pathlib import Path

import pyautogui
import mss  # type: ignore[import-not-found]
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


class GuiMouseMoveClick(BaseTool):
    name = "gui_mouse_move_click"
    description = "Move the mouse to (x, y) and optionally click."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        x = tool_input.parameters.get("x")
        y = tool_input.parameters.get("y")
        if x is None or y is None:
            return self._failure("x and y are required")

        click = bool(tool_input.parameters.get("click", False))
        button = tool_input.parameters.get("button", "left")
        clicks = int(tool_input.parameters.get("clicks", 1))
        duration = float(tool_input.parameters.get("duration", 0.2))

        try:
            pyautogui.moveTo(int(x), int(y), duration=duration)
            if click:
                pyautogui.click(int(x), int(y), button=button, clicks=clicks)
            return self._success(f"Moved to ({x}, {y})" + (" and clicked" if click else ""))
        except Exception as exc:
            return self._failure(str(exc))


class GuiTypeText(BaseTool):
    name = "gui_type_text"
    description = "Type a string using the keyboard."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        text = tool_input.parameters.get("text", "")
        interval = float(tool_input.parameters.get("interval", 0.0))
        try:
            pyautogui.write(text, interval=interval)
            return self._success(f"Typed {len(text)} characters")
        except Exception as exc:
            return self._failure(str(exc))


class GuiPressHotkey(BaseTool):
    name = "gui_press_hotkey"
    description = "Press a combination of keys (e.g., ctrl+c)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        keys = tool_input.parameters.get("keys", [])
        if not keys:
            return self._failure("keys is required")
        try:
            pyautogui.hotkey(*keys)
            return self._success(f"Pressed hotkey: {'+'.join(keys)}")
        except Exception as exc:
            return self._failure(str(exc))


class GuiTakeScreenshot(BaseTool):
    name = "gui_take_screenshot"
    description = "Take a screenshot of the entire screen or a region."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        output_path = tool_input.parameters.get("output_path", "screenshot.png")
        region = tool_input.parameters.get("region")

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
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
                img.save(save_path)
            return self._success(
                f"Screenshot saved to {save_path.name}",
                data={"path": str(save_path)},
            )
        except Exception as exc:
            return self._failure(str(exc))


class GuiGetMousePosition(BaseTool):
    name = "gui_get_mouse_position"
    description = "Return current mouse cursor coordinates."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            pos = pyautogui.position()
            return self._success(
                "Mouse position retrieved",
                data={"x": pos.x, "y": pos.y},
            )
        except Exception as exc:
            return self._failure(str(exc))
