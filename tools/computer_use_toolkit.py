"""Advanced GUI/computer-use tools."""

from __future__ import annotations

import asyncio
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, cast

try:
    import imageio.v2 as imageio  # type: ignore[import-not-found]
except Exception:
    try:
        import imageio  # type: ignore[import-not-found]
    except Exception:
        imageio = None

try:
    import mss  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional backend
    mss = None  # type: ignore[assignment]

try:
    import pyautogui
except (ImportError, Exception):
    pyautogui = None  # type: ignore[assignment]

from PIL import Image  # type: ignore[import-not-found]

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_desktop_path
from tools.vision_toolkit import REGION_TEXT_PROMPT, analyze_image_with_gemini


def _resolve_sandboxed(path_str: str) -> Path:
    raw = (path_str or "").strip()
    if not raw:
        return resolve_desktop_path()
    # Always ensure Desktop prefix for bare filenames (e.g. "screenshot.png")
    if not any(sep in raw for sep in ("\\", "/", ":")):
        raw = f"Desktop/{raw}"
    return resolve_desktop_path(raw)


class GuiScreenshot(BaseTool):
    """Capture desktop screenshot, defaulting directly to user's Desktop folder."""

    name = "gui_screenshot"
    description = (
        "Capture a screenshot of the entire desktop or window and save to file. "
        "Defaults to Desktop (Desktop/screenshot.png). "
        "Parameters: output_path (optional save path), app_name (optional window title to focus)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from tools.gui_automation_toolkit import GuiTakeScreenshot

        return await GuiTakeScreenshot().execute(tool_input)


class ScreenCapture(GuiScreenshot):
    """Alias for GuiScreenshot for compatibility."""

    name = "screen_capture"


def _is_opencv_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return "opencv" in text or "cv2" in text


def _locate_center_on_screen(target: Path, confidence: float) -> tuple[Any, str]:
    kwargs: dict[str, Any] = {}
    if confidence > 0:
        kwargs["confidence"] = confidence
    point = pyautogui.locateCenterOnScreen(str(target), **kwargs)
    return point, ("opencv_confidence" if "confidence" in kwargs else "pixel_exact")


def _safe_locate_center_on_screen(target: Path, confidence: float) -> tuple[Any, str]:
    try:
        return _locate_center_on_screen(target, confidence)
    except Exception as exc:
        if not _is_opencv_missing(exc):
            raise
        try:
            point = pyautogui.locateCenterOnScreen(str(target))
            return point, "pixel_exact_no_cv2"
        except Exception as fallback_exc:
            if _is_opencv_missing(fallback_exc):
                raise RuntimeError(
                    "opencv-python eksik. confidence tabanli esleme kullanilamadi. "
                    "Lutfen `pip install opencv-python` ile yukleyin."
                ) from fallback_exc
            raise


class GuiClickImageOnScreen(BaseTool):
    name = "gui_click_image_on_screen"
    description = "Find an image on screen and click it."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        image_path = str(self._first_param(params, "image_path", "path", default=""))
        confidence = float(self._first_param(params, "confidence", default=0.8) or 0.8)
        scroll_retries = int(self._first_param(params, "scroll_retries", default=3) or 3)
        scroll_clicks = int(self._first_param(params, "scroll_clicks", default=-700) or -700)
        ocr_fallback = bool(self._first_param(params, "ocr_fallback", default=True))
        if not image_path:
            return self._failure("image_path is required")
        try:
            target = _resolve_sandboxed(image_path)
            point = None
            locate_method = "template"
            attempts = max(0, scroll_retries) + 1
            for attempt in range(1, attempts + 1):
                point, locate_method = await asyncio.to_thread(
                    _safe_locate_center_on_screen,
                    target,
                    confidence,
                )
                if point is not None:
                    await asyncio.to_thread(pyautogui.click, point.x, point.y)
                    return self._success(
                        "Image found and clicked",
                        data={
                            "x": point.x,
                            "y": point.y,
                            "method": locate_method,
                            "attempt": attempt,
                        },
                    )
                if attempt < attempts:
                    await asyncio.to_thread(pyautogui.scroll, scroll_clicks)
                    await asyncio.to_thread(time.sleep, 0.25)

            if ocr_fallback:
                desc = str(
                    self._first_param(
                        params,
                        "target",
                        "description",
                        "query",
                        default=Path(image_path).stem,
                    )
                ).strip()
                result = await asyncio.to_thread(_locate_and_click_via_vision, desc)
                return self._success("OCR fallback clicked target", data={**result, "method": "vision_ocr"})

            return self._failure("Image not found on screen")
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
        output_path = str(self._first_param(params, "output_path", "path", default="screen_record.mp4"))
        try:
            save_path = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_record_screen, save_path, seconds, fps)
            return self._success("Screen recording saved", data={"path": str(save_path)})
        except Exception as exc:
            return self._failure(str(exc))


class MediaScreenRecordInvisible(BaseTool):
    name = "media_screen_record_invisible"
    description = "Start/stop stealth screen recording in background while other tools run."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", default="start")).lower()
        if action == "start":
            output_path = str(self._first_param(params, "output_path", "path", default="screen_record_invisible.mp4"))
            fps = int(self._first_param(params, "fps", default=5) or 5)
            try:
                save_path = _resolve_sandboxed(output_path)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                started = _start_background_recording(save_path, fps)
                if not started:
                    return self._failure("background recording is already running")
                return self._success(
                    "Background screen recording started",
                    data={"path": str(save_path), "fps": fps, "recording": True},
                )
            except Exception as exc:
                return self._failure(str(exc))

        if action == "stop":
            try:
                stop_result = await asyncio.to_thread(_stop_background_recording)
                if not stop_result.get("ok"):
                    return self._failure(str(stop_result.get("error") or "recording not running"))
                return self._success(
                    "Background screen recording stopped",
                    data=stop_result,
                )
            except Exception as exc:
                return self._failure(str(exc))

        return self._failure("Unsupported action. Use start|stop")


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
        output_path = str(self._first_param(params, "output_path", "path", default="region_ocr.png"))
        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_capture_region, save_path, region)
            text = await asyncio.to_thread(analyze_image_with_gemini, save_path, REGION_TEXT_PROMPT)
            max_chars = int(self._first_param(params, "max_chars", default=20_000) or 20_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return self._success("Region analysis completed", data={"path": str(save_path), "text": text})
        except Exception as exc:
            return self._failure(str(exc))


class GuiLocateAndClick(BaseTool):
    name = "gui_locate_and_click"
    description = (
        "Take a screenshot, use Gemini vision to locate a described UI element, and click its center coordinates."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        image_path_value = str(self._first_param(params, "image_path", "path", default="")).strip()
        confidence = float(self._first_param(params, "confidence", default=0.8) or 0.8)

        if image_path_value:
            try:
                target = _resolve_sandboxed(image_path_value)
                point, locate_method = await asyncio.to_thread(
                    _safe_locate_center_on_screen,
                    target,
                    confidence,
                )
                if point is None:
                    return self._failure("Image not found on screen")
                await asyncio.to_thread(pyautogui.click, point.x, point.y)
                return self._success(
                    "Image found and clicked",
                    data={"x": point.x, "y": point.y, "method": locate_method},
                )
            except Exception as exc:
                return self._failure(str(exc))

        element_desc = str(self._first_param(params, "element", "description", "target", "text", "label", default=""))
        if not element_desc:
            return self._failure("element description is required")
        try:
            result = await asyncio.to_thread(_locate_and_click_via_vision, element_desc)
            return self._success(
                f"Clicked element: {element_desc}",
                data=result,
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

    if mss is not None:
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[0]
                for _ in range(frame_count):
                    shot = sct.grab(monitor)
                    frames.append(Image.frombytes("RGB", shot.size, shot.rgb))
                    time.sleep(1 / max(1, fps))
        except Exception:
            frames = []

    if not frames:
        for _ in range(frame_count):
            frames.append(_capture_frame_dotnet())
            time.sleep(1 / max(1, fps))

    with imageio.get_writer(path, format=cast(Any, "FFMPEG"), fps=fps) as writer:
        append_data = cast(Any, writer).append_data
        for frame in frames:
            append_data(frame)


def _capture_frame_dotnet() -> Image.Image:
    if os.name != "nt":
        raise RuntimeError(".NET screen capture is only available on Windows")

    temp_path = Path(tempfile.gettempdir()) / "omnicore_frame_capture.png"
    escaped = str(temp_path).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$vs=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
        "$bmp=New-Object System.Drawing.Bitmap $vs.Width,$vs.Height; "
        "$gfx=[System.Drawing.Graphics]::FromImage($bmp); "
        "$gfx.CopyFromScreen($vs.Left,$vs.Top,0,0,$bmp.Size,"
        "[System.Drawing.CopyPixelOperation]::SourceCopy); "
        f"$bmp.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$gfx.Dispose(); $bmp.Dispose();"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "dotnet frame capture failed").strip())

    with Image.open(temp_path) as img:
        frame = img.copy()
    try:
        temp_path.unlink(missing_ok=True)
    except Exception:
        pass
    return frame


def _capture_region(path: Path, region: dict[str, int]) -> None:
    if region["width"] <= 0 or region["height"] <= 0:
        raise ValueError("width and height must be greater than zero")
    if mss is not None:
        mss_backend = cast(Any, mss)
        with mss_backend.mss() as sct:
            shot = sct.grab(region)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
            image.save(path)
        return

    if os.name != "nt":
        raise RuntimeError("Region capture requires mss on non-Windows platforms")

    left = int(region["left"])
    top = int(region["top"])
    width = int(region["width"])
    height = int(region["height"])
    escaped = str(path).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$left={left}; $top={top}; $width={width}; $height={height}; "
        "$bmp=New-Object System.Drawing.Bitmap $width,$height; "
        "$gfx=[System.Drawing.Graphics]::FromImage($bmp); "
        "$gfx.CopyFromScreen($left,$top,0,0,$bmp.Size,"
        "[System.Drawing.CopyPixelOperation]::SourceCopy); "
        f"$bmp.Save('{escaped}', [System.Drawing.Imaging.ImageFormat]::Png); "
        "$gfx.Dispose(); $bmp.Dispose();"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "dotnet region capture failed").strip())


def _locate_and_click_via_vision(element_desc: str) -> dict[str, Any]:
    """Screenshot the screen, ask Gemini to find the element, click its center.

    Gemini is prompted to return the bounding box as JSON
    ``{"x": <center_x>, "y": <center_y>}`` for the described element.
    """
    import json as _json
    import tempfile

    # Capture full screen.
    if mss is not None:
        mss_backend = cast(Any, mss)
        with mss_backend.mss() as sct:
            monitor = sct.monitors[0]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
    else:
        img = _capture_frame_dotnet()

    tmp_path = Path(tempfile.gettempdir()) / "omnicore_locate_click.png"
    img.save(tmp_path)

    prompt = (
        f"Ekran görüntüsünde şu UI öğesini bul: '{element_desc}'. "
        "Öğenin merkez koordinatlarını piksel cinsinden döndür. "
        'Yanıtı YALNIZCA şu JSON formatında ver: {"x": <int>, "y": <int>}. '
        "Başka hiçbir şey yazma."
    )
    raw = analyze_image_with_gemini(tmp_path, prompt)

    # Parse coordinates from Gemini response.
    # Strip markdown fences if present.
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    coords = _json.loads(text)
    x = int(coords["x"])
    y = int(coords["y"])

    pyautogui.click(x, y)
    return {"x": x, "y": y, "element": element_desc}


_BACKGROUND_RECORDER: dict[str, Any] = {
    "task": None,
    "path": None,
    "fps": 5,
    "stop": False,
}


def _start_background_recording(path: Path, fps: int) -> bool:
    task = _BACKGROUND_RECORDER.get("task")
    if task is not None and not task.done():
        return False

    _BACKGROUND_RECORDER["path"] = path
    _BACKGROUND_RECORDER["fps"] = max(1, int(fps))
    _BACKGROUND_RECORDER["stop"] = False
    _BACKGROUND_RECORDER["task"] = asyncio.create_task(_background_record_loop())
    return True


async def _background_record_loop() -> None:
    path = cast(Path, _BACKGROUND_RECORDER["path"])
    fps = int(_BACKGROUND_RECORDER.get("fps", 5) or 5)
    frame_interval = 1.0 / max(1, fps)

    with imageio.get_writer(path, format=cast(Any, "FFMPEG"), fps=fps) as writer:
        append_data = cast(Any, writer).append_data
        if mss is not None:
            mss_backend = cast(Any, mss)
            with mss_backend.mss() as sct:
                monitor = sct.monitors[0]
                while not _BACKGROUND_RECORDER.get("stop"):
                    shot = await asyncio.to_thread(sct.grab, monitor)
                    frame = Image.frombytes("RGB", shot.size, shot.rgb)
                    append_data(frame)
                    await asyncio.sleep(frame_interval)
        else:
            while not _BACKGROUND_RECORDER.get("stop"):
                frame = await asyncio.to_thread(_capture_frame_dotnet)
                append_data(frame)
                await asyncio.sleep(frame_interval)


def _stop_background_recording() -> dict[str, Any]:
    task = _BACKGROUND_RECORDER.get("task")
    if task is None or task.done():
        _BACKGROUND_RECORDER["task"] = None
        _BACKGROUND_RECORDER["path"] = None
        return {"ok": False, "error": "background recording not running"}

    _BACKGROUND_RECORDER["stop"] = True
    try:
        task.cancel()
        if not task.done():
            task.get_loop().call_soon_threadsafe(lambda: None)
    except Exception:
        pass

    path = _BACKGROUND_RECORDER.get("path")
    _BACKGROUND_RECORDER["task"] = None
    _BACKGROUND_RECORDER["path"] = None
    return {"ok": True, "path": str(path) if path else "", "recording": False}


class GuiInspectWindows(BaseTool):
    """List open active windows on the desktop."""

    name = "gui_inspect_windows"
    description = "List all open desktop application windows, titles, and handles."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            windows = await asyncio.to_thread(_list_desktop_windows)
            return self._success(
                f"Found {len(windows)} active desktop windows.",
                data={"windows": windows, "count": len(windows)},
            )
        except Exception as exc:
            return self._failure(f"Failed to inspect windows: {exc}")


class GuiFocusWindow(BaseTool):
    """Focus and bring a specific window to the foreground."""

    name = "gui_focus_window"
    description = (
        "Focus and bring a target window to foreground by title or process name. "
        "Parameters: title (partial window title or app name)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        title = str(self._first_param(params, "title", "name", "app", default="") or "").strip()
        if not title:
            return self._failure("title parameter is required.")

        try:
            focused = await asyncio.to_thread(_focus_window_by_title, title)
            if focused:
                return self._success(f"Window '{title}' focused.", data={"title": title})
            return self._failure(f"Window matching '{title}' not found.")
        except Exception as exc:
            return self._failure(f"Failed to focus window: {exc}")


def _list_desktop_windows() -> list[dict[str, str]]:
    windows: list[dict[str, str]] = []
    try:
        import pygetwindow as gw

        for w in gw.getAllWindows():
            if w.title and w.title.strip():
                windows.append({"title": w.title.strip(), "visible": str(w.visible)})
        if windows:
            return windows
    except Exception:
        pass

    # Powershell fallback
    try:
        ps_cmd = (
            "Get-Process | Where-Object {$_.MainWindowTitle} | "
            "Select-Object ProcessName, MainWindowTitle | ConvertTo-Json"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.stdout.strip():
            import json

            data = json.loads(res.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                windows.append(
                    {
                        "title": item.get("MainWindowTitle", ""),
                        "process": item.get("ProcessName", ""),
                    }
                )
    except Exception:
        pass

    return windows


def _focus_window_by_title(title: str) -> bool:
    try:
        import pygetwindow as gw

        matches = gw.getWindowsWithTitle(title)
        if matches:
            matches[0].activate()
            return True
    except Exception:
        pass

    try:
        cmd = (
            f"$w = Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}} | "
            f"Select-Object -First 1; "
            f"if ($w) {{ (New-Object -ComObject WScript.Shell).AppActivate($w.Id) }}"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return res.returncode == 0
    except Exception:
        return False
