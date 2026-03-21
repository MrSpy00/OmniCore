"""GUI Automation Toolkit — mouse, keyboard, and screenshots."""

from __future__ import annotations

from pathlib import Path

import mss  # type: ignore[import-not-found]
import pyautogui
from PIL import Image  # type: ignore[import-not-found]

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


def _resolve_output_target(path_str: str) -> Path:
    raw = (path_str or "").strip()
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    target, _ = resolve_user_path(raw)
    return target


class GuiMouseMoveClick(BaseTool):
    name = "gui_mouse_move_click"
    description = "Move the mouse to (x, y) and optionally click."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        x = self._first_param(params, "x")
        y = self._first_param(params, "y")
        if x is None or y is None:
            return self._failure("x and y are required")

        click = bool(params.get("click", False))
        button = params.get("button", "left")
        clicks = int(params.get("clicks", 1))
        duration = float(params.get("duration", 0.2))

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
        params = self._params(tool_input)
        text = str(self._first_param(params, "text", "value", default=""))
        interval = float(params.get("interval", 0.0))
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
        params = self._params(tool_input)
        keys = self._first_param(params, "keys", "hotkey", "key", default=[])
        if isinstance(keys, str):
            normalized = keys.replace("+", " ").replace(",", " ").split()
            keys = normalized if normalized else [keys]
        if not keys:
            return self._failure("keys is required")
        try:
            key_list = [str(k).strip() for k in keys if str(k).strip()]
            if not key_list:
                return self._failure("keys is required")
            pyautogui.hotkey(*key_list)
            return self._success(f"Pressed hotkey: {'+'.join(key_list)}")
        except Exception as exc:
            return self._failure(str(exc))


class GuiScrollMouse(BaseTool):
    name = "gui_scroll_mouse"
    description = "Scroll mouse wheel by a number of clicks."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        clicks = self._first_param(params, "clicks", "amount", "delta", default=0)
        x = self._first_param(params, "x")
        y = self._first_param(params, "y")

        try:
            clicks_int = int(clicks)
        except Exception:
            return self._failure("clicks must be an integer")

        try:
            if x is not None and y is not None:
                pyautogui.moveTo(int(x), int(y), duration=0.1)
            pyautogui.scroll(clicks_int)
            return self._success(
                f"Scrolled mouse by {clicks_int} clicks",
                data={"clicks": clicks_int, "x": x, "y": y},
            )
        except Exception as exc:
            return self._failure(str(exc))


class GuiTakeScreenshot(BaseTool):
    name = "gui_take_screenshot"
    description = "Take a screenshot of the entire screen or a region."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        output_path = self._first_param(
            params, "output_path", "file_path", "path", default="screenshot.png"
        )
        region = params.get("region")
        if isinstance(region, str):
            region = None

        try:
            save_path = _resolve_output_target(str(output_path))
            if save_path.exists() and save_path.is_dir():
                save_path = save_path / "screenshot.png"
            elif str(output_path).strip().lower() in {"desktop", "downloads", "documents"}:
                save_path = _resolve_output_target(str(output_path)) / "screenshot.png"
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
