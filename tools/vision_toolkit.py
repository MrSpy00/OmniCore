"""Vision Toolkit — screen capture + OCR analysis."""

from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Any, cast

import mss  # type: ignore[import-not-found]

try:
    import pyautogui
except (ImportError, Exception):
    pyautogui = None  # type: ignore[assignment]

from google import genai
from google.genai import types
from PIL import Image  # type: ignore[import-not-found]

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path

SCREEN_ANALYSIS_PROMPT = (
    "Read all visible text on this screen exactly. If there is no readable text, briefly describe the visible UI."
)
TARGET_LOCATE_PROMPT = (
    "Find the target UI element described by the user. "
    "Return ONLY strict JSON with keys: x, y, found, confidence, reason. "
    "x and y must be integer center coordinates in current screenshot pixel space. "
    "If not found, return found=false and x=0,y=0."
)
REGION_TEXT_PROMPT = (
    "Read all visible text in this screenshot region exactly. If there is no readable text, "
    "briefly describe the visible UI in the region."
)


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value))
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except Exception:
        return default


def _focus_window_by_title(title: str) -> bool:
    """Try to bring a window matching title to foreground. Returns True if successful."""
    if not title.strip():
        return False
    try:
        from tools.base import force_window_foreground

        result = force_window_foreground(title, timeout_seconds=3.0)
        return bool(result.get("activated", False))
    except Exception:
        return False


def _get_window_bbox(title: str) -> dict[str, int] | None:
    """Get bounding box of a window by title for region capture."""
    if not title.strip():
        return None
    try:
        import pygetwindow as gw  # type: ignore[import-not-found]

        windows = gw.getWindowsWithTitle(title)
        if windows:
            w = windows[0]
            if w.width > 0 and w.height > 0:
                return {"left": w.left, "top": w.top, "width": w.width, "height": w.height}
    except Exception:
        pass
    return None


class GuiAnalyzeScreen(BaseTool):
    name = "gui_analyze_screen"
    description = "Take a screenshot and extract visible text using Gemini vision."
    is_destructive = False  # Read-only operation, no approval needed

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        # Default to Desktop/screenshot for easy access
        output_path = str(self._first_param(params, "output_path", "path", default="Desktop/screenshot.png"))
        region = params.get("region")
        if isinstance(region, str):
            region = None
        target = str(self._first_param(params, "target", "element", "query", default="") or "").strip()
        # app_name: window title to focus BEFORE taking screenshot
        app_name = str(self._first_param(params, "app", "app_name", "application", "window", default="") or "").strip()
        click = bool(params.get("click", False))
        verify_after_click = bool(params.get("verify_after_click", False))
        max_attempts = int(params.get("max_attempts", 2) or 2)
        scroll_retries = int(params.get("scroll_retries", 3) or 3)
        scroll_clicks = int(params.get("scroll_clicks", -700) or -700)

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Focus target window BEFORE capturing if app_name is specified
            if app_name:
                await asyncio.to_thread(_focus_window_by_title, app_name)
                await asyncio.to_thread(time.sleep, 0.8)  # Let window come to foreground
                # Try to get window bounds for region capture
                if region is None:
                    window_bbox = await asyncio.to_thread(_get_window_bbox, app_name)
                    if window_bbox:
                        region = window_bbox

            text = ""
            max_chars = int(params.get("max_chars", 20_000))
            payload: dict[str, Any] = {"path": str(save_path), "text": text}
            if app_name:
                payload["focused_app"] = app_name

            locator_attempts: list[dict[str, Any]] = []
            located: dict[str, Any] | None = None
            attempts = max(0, scroll_retries) + 1

            for attempt in range(1, attempts + 1):
                # Re-focus window before each retry if scrolling happened
                if app_name and attempt > 1:
                    await asyncio.to_thread(_focus_window_by_title, app_name)
                    await asyncio.to_thread(time.sleep, 0.3)
                await asyncio.to_thread(_capture_screen, save_path, region)
                text = await asyncio.to_thread(analyze_image_with_gemini, save_path, SCREEN_ANALYSIS_PROMPT)
                if len(text) > max_chars:
                    text = text[:max_chars] + "\n... (truncated)"
                payload["text"] = text

                if not target:
                    break

                located = await asyncio.to_thread(_locate_target_with_vision, save_path, target)
                located_conf = _as_float(located.get("confidence", 0.0), 0.0)
                located_x = _as_int(located.get("x", 0), 0)
                located_y = _as_int(located.get("y", 0), 0)
                locator_attempts.append(
                    {
                        "attempt": attempt,
                        "found": bool(located.get("found")),
                        "confidence": located_conf,
                        "x": located_x,
                        "y": located_y,
                    }
                )

                if bool(located.get("found")):
                    break

                if attempt < attempts:
                    if pyautogui is not None:
                        await asyncio.to_thread(pyautogui.scroll, scroll_clicks)
                    await asyncio.to_thread(time.sleep, 0.25)

            if target:
                payload["target"] = target
                payload["locator"] = located or {
                    "found": False,
                    "x": 0,
                    "y": 0,
                    "confidence": 0.0,
                    "reason": "Target not found after scroll retries",
                }
                payload["locator_attempts"] = locator_attempts

                if click and located and bool(located.get("found")):
                    click_result = await asyncio.to_thread(
                        _click_with_self_correction,
                        _as_int(located.get("x", 0), 0),
                        _as_int(located.get("y", 0), 0),
                        target,
                        max(1, max_attempts),
                        verify_after_click,
                    )
                    payload["action"] = click_result

            return self._success("Screen analyzed", data=payload)
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


def analyze_image_with_gemini(path: Path, prompt: str = SCREEN_ANALYSIS_PROMPT) -> str:
    settings = get_settings()
    api_keys = settings.google_api_keys
    if not any(k.strip() for k in api_keys):
        raise RuntimeError("GOOGLE_API_KEY is required for vision analysis")
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")

    last_exc: Exception | None = None
    for idx, key in enumerate(api_keys, start=1):
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    prompt,
                    types.Part.from_bytes(data=base64.b64decode(encoded), mime_type="image/png"),
                ],
            )
            text = getattr(response, "text", "")
            if text:
                return text
            raise RuntimeError("Vision model returned empty output")
        except Exception as exc:
            last_exc = exc
            detail = str(exc).lower()
            retryable = any(
                marker in detail
                for marker in (
                    "429",
                    "quota",
                    "resource_exhausted",
                    "rate limit",
                    "too many requests",
                )
            )
            if retryable and idx < len(api_keys):
                continue
            if retryable:
                raise RuntimeError(
                    "Vision quota exhausted across all configured Gemini keys; fallback to GUI/CLI flow is required"
                ) from exc
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Vision analysis failed")


def _locate_target_with_vision(path: Path, target: str) -> dict[str, Any]:
    prompt = f"{TARGET_LOCATE_PROMPT} Target description: {target}"
    raw = analyze_image_with_gemini(path, prompt)
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

    parsed = cast(dict[str, Any], json.loads(text))
    found = bool(parsed.get("found", False))
    x = _as_int(parsed.get("x", 0), 0)
    y = _as_int(parsed.get("y", 0), 0)
    confidence = _as_float(parsed.get("confidence", 0.0), 0.0)
    reason = str(parsed.get("reason", "") or "")
    return {
        "found": found,
        "x": x,
        "y": y,
        "confidence": confidence,
        "reason": reason,
        "raw": raw[:4000],
    }


def _click_with_self_correction(
    x: int,
    y: int,
    target: str,
    max_attempts: int,
    verify_after_click: bool,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    current_x = x
    current_y = y

    for attempt in range(1, max_attempts + 1):
        if pyautogui is not None:
            pyautogui.click(current_x, current_y)
        entry: dict[str, object] = {"attempt": attempt, "x": current_x, "y": current_y}

        if not verify_after_click:
            entry["status"] = "clicked"
            attempts.append(entry)
            return {"status": "clicked", "attempts": attempts}

        temp_path = Path(pathlib_temp_dir()) / "vision_verify_after_click.png"
        _capture_screen(temp_path, None)
        locator = cast(dict[str, Any], _locate_target_with_vision(temp_path, target))
        entry["verify_found"] = bool(locator.get("found"))
        entry["verify_confidence"] = _as_float(locator.get("confidence", 0.0), 0.0)

        if not bool(locator.get("found")):
            entry["status"] = "completed"
            attempts.append(entry)
            return {"status": "completed", "attempts": attempts}

        current_x = _as_int(locator.get("x", current_x), current_x)
        current_y = _as_int(locator.get("y", current_y), current_y)
        entry["status"] = "retry"
        attempts.append(entry)

    return {"status": "max_attempts_reached", "attempts": attempts}


def pathlib_temp_dir() -> str:
    import tempfile

    return tempfile.gettempdir()


class VisionInstantScreenContext(BaseTool):
    """'Ekrana Bak' (Instant Visual Screen Context) — captures active screen/window and explains the content."""

    name = "vision_instant_screen_context"
    description = (
        "Capture the active desktop or window screen and analyze its contents, error messages, "
        "code, or layout using multimodal Vision AI."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        default_prompt = "Bu ekranda ne görünüyor? Herhangi bir hata veya önemli içeriği detaylı açıkla."
        prompt = self._first_param(params, "prompt", "question", "query") or default_prompt
        window_title = self._first_param(params, "window_title", "window") or ""

        if window_title:
            await asyncio.to_thread(_focus_window_by_title, str(window_title))
            await asyncio.sleep(0.3)

        def _worker() -> dict[str, Any]:
            temp_img = Path(pathlib_temp_dir()) / "omnicore_instant_screen.png"
            _capture_screen(temp_img, None)

            analysis = analyze_image_with_gemini(temp_img, str(prompt))
            return {
                "screenshot_path": str(temp_img),
                "analysis": analysis,
                "window": window_title or "Active Desktop",
            }

        res = await asyncio.to_thread(_worker)
        return self._success(
            f"Ekran Analizi ({res['window']}):\n\n{res['analysis']}",
            data=res,
        )


def _compute_dynamic_grid(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Çözünürlüğe göre dinamik grid boyutu hesaplar.

    Minimum hücre alanı ~25000px² — vision model'lerin okuyabileceği kadar büyük.
    1920x1080 → (5, 9) = 45 hücre
    2560x1440 → (6, 12) = 72 hücre
    3840x2160 → (8, 16) = 128 hücre
    """
    min_cell_area = 25000
    total_area = screen_width * screen_height

    rows = max(3, min(10, int((total_area / min_cell_area / (screen_width / screen_height)) ** 0.5)))
    cols = max(4, min(20, int(rows * (screen_width / screen_height))))
    return rows, cols


class VisionSetOfMarkAnnotate(BaseTool):
    """Çözünürlüğe göre dinamik boyutlu Set-of-Mark ekran işaretlemesi oluşturur."""

    name = "vision_som_annotate"
    description = (
        "Capture screen and overlay numbered visual marker badges (Set-of-Mark) on interactive elements. "
        "Grid size adapts dynamically to screen resolution for optimal vision model consumption."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        out_param = self._first_param(params, "output_path", "path")
        default_som = Path(pathlib_temp_dir()) / "som_annotated.png"
        output_file = _resolve_sandboxed(str(out_param)) if out_param else default_som

        def _worker() -> dict[str, Any]:
            from PIL import ImageDraw

            temp_raw = Path(pathlib_temp_dir()) / "som_raw.png"
            _capture_screen(temp_raw, None)

            with Image.open(temp_raw) as img:
                w, h = img.size
                draw = ImageDraw.Draw(img)

                rows, cols = _compute_dynamic_grid(w, h)
                cell_w = w // cols
                cell_h = h // rows

                marks: list[dict[str, Any]] = []
                mark_id = 1

                for r in range(rows):
                    for c in range(cols):
                        bx1 = c * cell_w + 4
                        by1 = r * cell_h + 4
                        bx2 = (c + 1) * cell_w - 4
                        by2 = (r + 1) * cell_h - 4
                        cx = (bx1 + bx2) // 2
                        cy = (by1 + by2) // 2

                        draw.rectangle([bx1, by1, bx2, by2], outline="#00FFCC", width=2)
                        draw.rectangle([bx1, by1, bx1 + 36, by1 + 24], fill="#000000", outline="#FF007F", width=2)
                        draw.text((bx1 + 8, by1 + 4), f"#{mark_id}", fill="#FFFFFF")

                        marks.append(
                            {
                                "id": mark_id,
                                "box": [bx1, by1, bx2, by2],
                                "center": (cx, cy),
                            }
                        )
                        mark_id += 1

                img.save(output_file)

            return {
                "output_path": str(output_file),
                "marks_count": len(marks),
                "grid": {"rows": rows, "cols": cols},
                "marks": marks,
            }

        res = await asyncio.to_thread(_worker)
        return self._success(
            f"Dinamik Set-of-Mark oluşturuldu ({res['grid']['rows']}×{res['grid']['cols']} grid, "
            f"{res['marks_count']} bölge). Dosya: {res['output_path']}",
            data=res,
        )
