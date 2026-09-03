"""Instant Vision Toolkit — Active window screen context and vision inspection."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_desktop_path

logger = get_logger(__name__)

try:
    import mss
    from PIL import Image

    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    import win32gui
    import win32process

    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


def _get_active_window_info() -> dict[str, Any]:
    """Retrieve title, class, bounds and PID of current active foreground window."""
    info: dict[str, Any] = {
        "hwnd": 0,
        "title": "",
        "class_name": "",
        "rect": None,
        "pid": 0,
    }
    if not _WIN32_AVAILABLE:
        return info

    try:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            info["hwnd"] = hwnd
            info["title"] = win32gui.GetWindowText(hwnd)
            info["class_name"] = win32gui.GetClassName(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            # rect is (left, top, right, bottom)
            width = max(0, rect[2] - rect[0])
            height = max(0, rect[3] - rect[1])
            info["rect"] = {
                "left": rect[0],
                "top": rect[1],
                "right": rect[2],
                "bottom": rect[3],
                "width": width,
                "height": height,
            }
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                info["pid"] = pid
            except Exception:
                pass
    except Exception as exc:
        logger.debug("instant_vision.get_active_window_error", error=str(exc))

    return info


def _capture_active_window_image(save_path: Path | None = None) -> Path:
    """Capture foreground window screenshot or full screen if no valid bounds."""
    if not _MSS_AVAILABLE:
        raise RuntimeError("mss and PIL are required for screen capture")

    window_info = _get_active_window_info()
    rect = window_info.get("rect")

    target_path = save_path or resolve_desktop_path("instant_screen.png")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with mss.mss() as sct:
        if rect and rect["width"] > 80 and rect["height"] > 80 and rect["left"] >= -500 and rect["top"] >= -500:
            monitor = {
                "top": rect["top"],
                "left": rect["left"],
                "width": rect["width"],
                "height": rect["height"],
            }
            sct_img = sct.grab(monitor)
        else:
            sct_img = sct.grab(sct.monitors[0])

        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        img.save(str(target_path), format="PNG")

    return target_path


class GetActiveWindowContext(BaseTool):
    """Retrieve detailed UI context, accessible text, and properties of the currently focused window."""

    name = "get_active_window_context"
    description = (
        "Inspect currently focused (active) window on Windows. Returns window title, "
        "process ID, bounding box, and accessible text elements extracted via UI Automation."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            info = await asyncio.to_thread(_get_active_window_info)
            uia_elements: list[dict[str, Any]] = []

            try:
                from tools.windows_uia_toolkit import _bridge

                if _bridge.available:
                    root = await asyncio.to_thread(_bridge.find_foreground_window)
                    if root:
                        tree = await asyncio.to_thread(_bridge.get_element_tree, root, max_depth=3, max_elements=40)
                        for elem in tree:
                            name = elem.get("name", "").strip()
                            if name:
                                uia_elements.append(
                                    {
                                        "name": name,
                                        "control_type": elem.get("control_type", ""),
                                        "automation_id": elem.get("automation_id", ""),
                                    }
                                )
            except Exception as exc:
                logger.debug("instant_vision.uia_failed", error=str(exc))

            summary = (
                f"Aktif Pencere: '{info.get('title')}' (PID: {info.get('pid')}, Sınıf: {info.get('class_name')})\n"
                f"Boyut: {info.get('rect', {}).get('width')}x{info.get('rect', {}).get('height')}\n"
                f"Bulunan Arayüz Metinleri ({len(uia_elements)} eleman): "
                + ", ".join(f"[{e['control_type']}: {e['name']}]" for e in uia_elements[:15])
            )
            return self._success(
                summary,
                data={
                    "window": info,
                    "elements": uia_elements,
                },
            )
        except Exception as exc:
            return self._failure(f"Pencere bilgisi alınamadı: {exc}")


class InstantScreenContext(BaseTool):
    """Analyze the currently visible active screen / window using Vision LLM."""

    name = "instant_screen_context"
    description = (
        "Capture the active window or screen and analyze its visual contents with Vision LLM. "
        "Use when user asks 'ekrana bak', 'şu an neye bakıyorum', or asks questions about the screen."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        prompt = str(self._first_param(params, "query", "prompt", "question", default="") or "").strip()
        if not prompt:
            prompt = (
                "Şu an ekranda/aktif pencerede ne görünüyor? "
                "Ana içeriği, açık olan uygulamayı ve önemli "
                "detayları özetle."
            )

        output_path = resolve_desktop_path("instant_screen.png")

        try:
            saved_path = await asyncio.to_thread(_capture_active_window_image, output_path)
            window_info = await asyncio.to_thread(_get_active_window_info)

            # Vision LLM Analysis
            analysis_text = ""
            try:
                from core.llm import LLMFactory
                from langchain_core.messages import HumanMessage

                llm = LLMFactory.create_chat_model()

                # Read image bytes and encode as base64
                with open(saved_path, "rb") as img_f:
                    img_b64 = base64.b64encode(img_f.read()).decode("utf-8")

                vision_message = HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": (
                                f"Görsel bağlamı: Aktif pencere '{window_info.get('title')}'.\nSoru/Talep: {prompt}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                    ]
                )
                response = await llm.ainvoke([vision_message])
                analysis_text = str(response.content).strip()
            except Exception as v_exc:
                logger.warning("instant_vision.llm_fallback", error=str(v_exc))
                analysis_text = (
                    f"Aktif pencere yakalandı ('{window_info.get('title')}'). "
                    f"Görsel analiz API erişilemedi, ekran görüntüsü {saved_path.name} olarak kaydedildi."
                )

            return self._success(
                f"Ekran Analizi: {analysis_text}",
                data={
                    "screenshot_path": str(saved_path),
                    "window_title": window_info.get("title"),
                    "analysis": analysis_text,
                },
            )
        except Exception as exc:
            return self._failure(f"Ekran analizi başarısız oldu: {exc}")
