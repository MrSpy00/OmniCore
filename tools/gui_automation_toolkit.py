"""GUI Automation Toolkit — mouse, keyboard, and screenshots."""

from __future__ import annotations

import subprocess
from pathlib import Path

try:
    import mss  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional backend
    mss = None  # type: ignore[assignment]

import pyautogui
from PIL import Image  # type: ignore[import-not-found]

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()


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
        values = list(params.values()) if params else []
        keys = (
            params.get("keys")
            or params.get("key")
            or params.get("hotkey")
            or (values[0] if values else [])
        )
        if isinstance(keys, str):
            normalized = keys.replace("+", " ").replace(",", " ").split()
            keys = normalized if normalized else [keys]
        if not keys:
            return self._failure("keys is required")
        try:
            key_list = [str(k).strip() for k in keys if str(k).strip()]
            if not key_list:
                return self._failure("keys is required")
            if _RUNTIME.is_windows:
                if any(k.lower() in {"win", "windows", "meta", "super"} for k in key_list):
                    _send_hotkey_user32_windows(key_list)
                else:
                    _send_hotkey_sendkeys_windows(key_list)
            else:
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
            if _RUNTIME.is_windows:
                try:
                    _capture_screen_dotnet(save_path, region if isinstance(region, dict) else None)
                except Exception as dotnet_exc:
                    try:
                        _capture_screen_mss(save_path, region if isinstance(region, dict) else None)
                    except Exception as mss_exc:
                        raise RuntimeError(
                            f"Screenshot capture failed (.NET + mss): {dotnet_exc}; {mss_exc}"
                        ) from mss_exc
            else:
                _capture_screen_mss(save_path, region if isinstance(region, dict) else None)

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


def _capture_screen_mss(path: Path, region: dict | None = None) -> None:
    if mss is None:
        raise RuntimeError("mss backend is unavailable")

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


def _capture_screen_dotnet(path: Path, region: dict | None = None) -> None:
    escaped_path = str(path).replace("'", "''")
    if region:
        left = int(region.get("left", 0))
        top = int(region.get("top", 0))
        width = int(region.get("width", 0))
        height = int(region.get("height", 0))
        if width <= 0 or height <= 0:
            raise ValueError("region width/height must be greater than zero")
        sizing = f"$left={left}; $top={top}; $width={width}; $height={height}; "
    else:
        sizing = (
            "$vs=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
            "$left=$vs.Left; $top=$vs.Top; $width=$vs.Width; $height=$vs.Height; "
        )

    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        + sizing
        + "$bmp=New-Object System.Drawing.Bitmap $width,$height; "
        "$gfx=[System.Drawing.Graphics]::FromImage($bmp); "
        "$gfx.CopyFromScreen($left,$top,0,0,$bmp.Size,"
        "[System.Drawing.CopyPixelOperation]::SourceCopy); "
        f"$bmp.Save('{escaped_path}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$gfx.Dispose(); $bmp.Dispose();"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stderr or completed.stdout or "dotnet capture failed").strip()
        )


def _send_hotkey_sendkeys_windows(keys: list[str]) -> None:
    send_seq = _keys_to_sendkeys_sequence(keys)
    escaped_seq = send_seq.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait('{escaped_seq}')"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "sendkeys failed").strip())


def _send_hotkey_user32_windows(keys: list[str]) -> None:
    vk_codes = [_key_to_vk(key) for key in keys]
    if any(code is None for code in vk_codes):
        unknown = [keys[i] for i, code in enumerate(vk_codes) if code is None]
        raise ValueError(f"Unsupported key(s) for user32 injection: {unknown}")

    vk_expr = ",".join(str(int(code or 0)) for code in vk_codes)
    script = (
        'Add-Type -TypeDefinition @"\n'
        "using System;\n"
        "using System.Runtime.InteropServices;\n"
        "public static class Keyboard {\n"
        '  [DllImport("user32.dll")]\n'
        "  public static extern void keybd_event("
        "byte bVk, byte bScan, int dwFlags, int dwExtraInfo);\n"
        "}\n"
        '"@ -Language CSharp; '
        f"$keys=@({vk_expr}); "
        "foreach($vk in $keys){ [Keyboard]::keybd_event([byte]$vk,0,0,0) }; "
        "Start-Sleep -Milliseconds 70; "
        "for($i=$keys.Count-1; $i -ge 0; $i--){ [Keyboard]::keybd_event([byte]$keys[$i],0,2,0) }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "user32 hotkey failed").strip())


def _keys_to_sendkeys_sequence(keys: list[str]) -> str:
    modifiers: list[str] = []
    main_key = ""
    for key in keys:
        normalized = key.strip().lower()
        if not normalized:
            continue
        if normalized in {"ctrl", "control"}:
            modifiers.append("^")
            continue
        if normalized == "alt":
            modifiers.append("%")
            continue
        if normalized == "shift":
            modifiers.append("+")
            continue
        if normalized in {"win", "windows", "meta", "super"}:
            raise ValueError("Windows key hotkeys must use user32 backend")
        main_key = _key_to_sendkeys_token(normalized)
        break

    if not main_key:
        raise ValueError("No primary key provided for hotkey")
    return "".join(modifiers) + main_key


def _key_to_sendkeys_token(key: str) -> str:
    mapping = {
        "enter": "{ENTER}",
        "return": "{ENTER}",
        "esc": "{ESC}",
        "escape": "{ESC}",
        "tab": "{TAB}",
        "space": " ",
        "backspace": "{BACKSPACE}",
        "delete": "{DELETE}",
        "home": "{HOME}",
        "end": "{END}",
        "pgup": "{PGUP}",
        "pageup": "{PGUP}",
        "pgdn": "{PGDN}",
        "pagedown": "{PGDN}",
        "up": "{UP}",
        "down": "{DOWN}",
        "left": "{LEFT}",
        "right": "{RIGHT}",
        "f1": "{F1}",
        "f2": "{F2}",
        "f3": "{F3}",
        "f4": "{F4}",
        "f5": "{F5}",
        "f6": "{F6}",
        "f7": "{F7}",
        "f8": "{F8}",
        "f9": "{F9}",
        "f10": "{F10}",
        "f11": "{F11}",
        "f12": "{F12}",
    }
    if key in mapping:
        return mapping[key]
    if len(key) == 1:
        return key
    return "{" + key.upper() + "}"


def _key_to_vk(key: str) -> int | None:
    k = key.strip().lower()
    fixed_map = {
        "win": 0x5B,
        "windows": 0x5B,
        "meta": 0x5B,
        "super": 0x5B,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "shift": 0x10,
        "enter": 0x0D,
        "return": 0x0D,
        "esc": 0x1B,
        "escape": 0x1B,
        "tab": 0x09,
        "space": 0x20,
    }
    fixed = fixed_map.get(k)
    if fixed is not None:
        return fixed

    if len(k) == 1:
        ch = k.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
    return None
