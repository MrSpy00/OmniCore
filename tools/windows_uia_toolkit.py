"""Windows UI Automation Toolkit — IUIAutomation COM tabanlı koordinatsız arayüz etkileşimi.

Eski sürümde win32gui.EnumChildWindows kullanılıyordu — sadece text/class substring eşleştirmesi yapılabiliyordu.
Bu sürümde IUIAutomation COM arayüzü kullanılarak AutomationId, ControlType, IsEnabled,
ValuePattern, InvokePattern gibi tam Windows Erişilebilirlik Ağacı erişimi sağlanır.
"""

from __future__ import annotations

import asyncio
import ctypes
from typing import Any

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, force_window_foreground
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()

try:
    import comtypes
    import comtypes.client

    _COM_AVAILABLE = True
except ImportError:
    _COM_AVAILABLE = False

try:
    import win32gui
except ImportError:
    win32gui = None

try:
    import pyautogui
except Exception:
    pyautogui = None


# ─── IUIAutomation COM Sarmalayıcı ───────────────────────────────────────────────


class _UIAutomationBridge:
    """IUIAutomation COM arayüzü için thread-safe sarmalayıcı.

     Windows UI Automation API'sine erişerek uygulama arayüzlerindeki
    但on元素leri AutomationId, ControlType, Name gibi güvenilir tanımlayıcılarla bulur.
    """

    def __init__(self) -> None:
        self._uia: Any = None
        self._root: Any = None
        self._initialized = False

        if _COM_AVAILABLE:
            try:
                self._uia = comtypes.client.CreateObject("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")
                self._root = self._uia.GetRootElement()
                self._initialized = True
            except Exception:
                self._uia = None
                self._root = None

    @property
    def available(self) -> bool:
        return self._initialized and self._uia is not None

    def find_window(self, title: str) -> Any | None:
        """Başlık dizesiyle eşleşen üst düzey pencereyi bulur."""
        if not self.available or not title.strip():
            return None
        try:
            condition = self._uia.CreatePropertyCondition(30005, title)
            element = self._root.FindFirst(4, condition)
            return element
        except Exception:
            return None

    def find_foreground_window(self) -> Any | None:
        """Mevcut ön plan penceresini döndürür."""
        if not self.available:
            return None
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return None
            condition = self._uia.CreatePropertyCondition(30003, hwnd)
            return self._root.FindFirst(4, condition)
        except Exception:
            return None

    def get_element_tree(self, root: Any, max_depth: int = 4, max_elements: int = 80) -> list[dict[str, Any]]:
        """UIA ağaç yapısını递归 olarak gezer ve eleman listesi döndürür.

        Her eleman için şunları içerir:
        - automation_id, name, control_type, class_name
        - is_enabled, is_offscreen
        - bounding_rect, center coordinates
        - supported_patterns (invoke, value, toggle, selection, vb.)
        """
        if not self.available or root is None:
            return []

        elements: list[dict[str, Any]] = []
        self._walk_tree(root, elements, 0, max_depth, max_elements)
        return elements

    def _walk_tree(
        self,
        element: Any,
        elements: list[dict[str, Any]],
        depth: int,
        max_depth: int,
        max_elements: int,
    ) -> None:
        if len(elements) >= max_elements or depth > max_depth:
            return

        try:
            info = self._extract_element_info(element)
            if info:
                elements.append(info)

            condition = self._uia.CreateTrueCondition()
            child = element.FindFirst(1, condition)
            while child is not None and len(elements) < max_elements:
                self._walk_tree(child, elements, depth + 1, max_depth, max_elements)
                next_child_condition = self._uia.CreateTrueCondition()
                child = child.FindNext(1, next_child_condition)
        except Exception:
            pass

    def _extract_element_info(self, element: Any) -> dict[str, Any] | None:
        """Tek bir UIA elemanından bilgi çıkarır."""
        try:
            name = element.CurrentName or ""
            automation_id = element.CurrentAutomationId or ""
            control_type = element.CurrentLocalizedControlType or ""
            class_name = element.CurrentClassName or ""
            is_enabled = bool(element.CurrentIsEnabled)
            is_offscreen = bool(element.CurrentIsOffscreen)

            try:
                rect = element.CurrentBoundingRectangle
                left, top, right, bottom = (
                    rect.left,
                    rect.top,
                    rect.right,
                    rect.bottom,
                )
            except Exception:
                left, top, right, bottom = 0, 0, 0, 0

            w = max(0, right - left)
            h = max(0, bottom - top)

            patterns = self._get_supported_patterns(element)

            return {
                "name": name,
                "automation_id": automation_id,
                "control_type": control_type,
                "class_name": class_name,
                "is_enabled": is_enabled,
                "is_offscreen": is_offscreen,
                "rect": {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "width": w,
                    "height": h,
                },
                "center": {"x": left + w // 2, "y": top + h // 2},
                "supported_patterns": patterns,
            }
        except Exception:
            return None

    def _get_supported_patterns(self, element: Any) -> list[str]:
        """Elemanın desteklediği UIA pattern'lerini döndürür."""
        pattern_ids = {
            10000: "Invoke",
            10002: "Value",
            10003: "Select",
            10005: "ExpandCollapse",
            10010: "Toggle",
            10014: "ScrollItem",
            10015: "GridItem",
            10017: "SelectionItem",
            10018: "Dock",
            10020: "Text",
            10022: "ItemContainer",
            10023: "VirtualizedItem",
        }
        supported: list[str] = []
        for pid, pname in pattern_ids.items():
            try:
                element.GetCurrentPattern(pid)
                supported.append(pname)
            except Exception:
                pass
        return supported

    def find_element_by(
        self,
        root: Any,
        *,
        automation_id: str = "",
        name: str = "",
        control_type: str = "",
        name_contains: str = "",
    ) -> Any | None:
        """UIA koşullarıyla belirli bir elemanı bulur.

        Eşleme önceliği: automation_id tam eşleşme > name tam eşleşme >
        name_contains (içerir) > control_type eşleşme.
        """
        if not self.available or root is None:
            return None

        if automation_id:
            condition = self._uia.CreatePropertyCondition(30004, automation_id)
            element = root.FindFirst(4, condition)
            if element:
                return element

        if name:
            condition = self._uia.CreatePropertyCondition(30005, name)
            element = root.FindFirst(4, condition)
            if element:
                return element

        if name_contains:
            elements = self.get_element_tree(root, max_depth=4, max_elements=100)
            name_lower = name_contains.lower()
            for el in elements:
                if name_lower in el.get("name", "").lower():
                    return self.find_element_by(root, name=el["name"])

        if control_type:
            condition = self._uia.CreatePropertyCondition(30003, control_type)
            element = root.FindFirst(4, condition)
            if element:
                return element

        return None

    def invoke_element(self, element: Any) -> bool:
        """InvokePattern ile elemana tıklar (buton, menü öğesi, vb.)."""
        if not self.available or element is None:
            return False
        try:
            invoke_pattern = element.GetCurrentPattern(10000)
            invoke_pattern.Invoke()
            return True
        except Exception:
            try:
                if win32gui:
                    hwnd = element.CurrentNativeWindowHandle
                    if hwnd:
                        import win32con

                        win32gui.SendMessage(int(hwnd), win32con.BM_CLICK, 0, 0)
                        return True
            except Exception:
                pass
        return False

    def set_value(self, element: Any, value: str) -> bool:
        """ValuePattern ile elemana metin girer."""
        if not self.available or element is None:
            return False
        try:
            value_pattern = element.GetCurrentPattern(10002)
            value_pattern.SetValue(value)
            return True
        except Exception:
            try:
                hwnd = element.CurrentNativeWindowHandle
                if hwnd and win32gui:
                    import win32con

                    win32gui.SendMessage(int(hwnd), win32con.WM_SETTEXT, 0, value)
                    return True
            except Exception:
                pass
        return False

    def get_value(self, element: Any) -> str:
        """ValuePattern veya Name özelliği ile elemanın metnini okur."""
        if not self.available or element is None:
            return ""
        try:
            value_pattern = element.GetCurrentPattern(10002)
            return value_pattern.CurrentValue or ""
        except Exception:
            try:
                return element.CurrentName or ""
            except Exception:
                return ""


# ─── Modül düzeyinde singleton ─────────────────────────────────────────────────────

_bridge: _UIAutomationBridge | None = None


def _get_bridge() -> _UIAutomationBridge:
    global _bridge
    if _bridge is None:
        _bridge = _UIAutomationBridge()
    return _bridge


# ─── Araç Sınıfları ───────────────────────────────────────────────────────────────


class WindowsInspectUIElements(BaseTool):
    """penceresindeki etkileşimli UI elemanlarını IUIAutomation ile inceler."""

    name = "windows_inspect_ui_elements"
    description = (
        "Inspect interactive UI elements (buttons, inputs, lists) in the active or specified window "
        "using Windows IUIAutomation COM. Returns AutomationId, ControlType, Name, bounding rect, "
        "and supported patterns for each element."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows işletim sistemlerinde desteklenir.")

        params = self._params(tool_input)
        window_title = self._first_param(params, "window_title", "app_name", "window") or ""
        max_elements = int(self._first_param(params, "max_elements") or 80)
        max_depth = int(self._first_param(params, "max_depth") or 4)
        include_invisible = bool(params.get("include_invisible", False))

        def _worker() -> dict[str, Any]:
            bridge = _get_bridge()
            if not bridge.available:
                return {"success": False, "error": "IUIAutomation COM arayüzü kullanılamıyor. comtypes yüklü mü?"}

            if window_title:
                hwnd_element = bridge.find_window(str(window_title))
                if not hwnd_element:
                    return {"success": False, "error": f"'{window_title}' başlıklı pencere bulunamadı."}
                root = hwnd_element
            else:
                root = bridge.find_foreground_window()
                if not root:
                    return {"success": False, "error": "Ön plan penceresi bulunamadı."}

            try:
                title = root.CurrentName or ""
            except Exception:
                title = ""

            try:
                rect = root.CurrentBoundingRectangle
            except Exception:
                rect = None

            elements = bridge.get_element_tree(root, max_depth=max_depth, max_elements=max_elements)

            if not include_invisible:
                elements = [e for e in elements if not e.get("is_offscreen", False)]

            return {
                "success": True,
                "window": {
                    "title": title,
                    "rect": {
                        "left": rect.left,
                        "top": rect.top,
                        "right": rect.right,
                        "bottom": rect.bottom,
                    }
                    if rect
                    else None,
                },
                "element_count": len(elements),
                "elements": elements,
            }

        res = await asyncio.to_thread(_worker)
        if not res.get("success"):
            return self._failure(str(res.get("error", "UI elemanları incelenemedi.")))

        summary = (
            f"Pencere: '{res['window']['title']}' — {res['element_count']} etkileşimli eleman bulundu (IUIAutomation)."
        )
        return self._success(summary, data=res)


class WindowsClickUIElement(BaseTool):
    """InvokePattern ile koordinatsız olarak UI elemanına tıklar."""

    name = "windows_click_ui_element"
    description = (
        "Click a UI element (button, menu, checkbox) using IUIAutomation InvokePattern "
        "for reliable clicking without coordinate dependency. Match by AutomationId, Name, or ControlType."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta desteklenir.")

        params = self._params(tool_input)
        element_name = str(self._first_param(params, "element_name", "element", "label", "button") or "").strip()
        automation_id = str(self._first_param(params, "automation_id", "auto_id") or "").strip()
        control_type = str(self._first_param(params, "control_type", "type") or "").strip()
        window_title = self._first_param(params, "window_title", "window") or ""

        if not element_name and not automation_id:
            return self._failure("Tıklanacak elemanı tanımlamak için element_name veya automation_id gerekli.")

        def _worker() -> dict[str, Any]:
            bridge = _get_bridge()
            if not bridge.available:
                return {"success": False, "error": "IUIAutomation COM arayüzü kullanılamıyor."}

            if window_title:
                root = bridge.find_window(str(window_title))
                if not root:
                    return {"success": False, "error": f"'{window_title}' penceresi bulunamadı."}
            else:
                root = bridge.find_foreground_window()
                if not root:
                    return {"success": False, "error": "Ön plan penceresi bulunamadı."}

            target = bridge.find_element_by(
                root,
                automation_id=automation_id,
                name=element_name,
                control_type=control_type,
                name_contains=element_name if not automation_id else "",
            )

            if not target:
                try:
                    win_title = root.CurrentName or ""
                except Exception:
                    win_title = "bilinmeyen"
                return {
                    "success": False,
                    "error": f"'{win_title}' penceresinde '{element_name}' elemanı bulunamadı.",
                }

            try:
                force_window_foreground(int(getattr(target, "CurrentNativeWindowHandle", 0) or 0))
            except Exception:
                pass

            clicked = bridge.invoke_element(target)

            try:
                name = target.CurrentName or element_name
            except Exception:
                name = element_name

            return {
                "success": clicked,
                "clicked_element": name,
                "window": window_title or "Ön plan",
                "method": "InvokePattern" if clicked else "bulundu ama tıklanamadı",
            }

        res = await asyncio.to_thread(_worker)
        if not res.get("success"):
            return self._failure(str(res.get("error", "Tıklama başarısız.")))

        msg = (
            f"'{res['window']}' penceresinde '{res['clicked_element']}' "
            f"elemanına başarıyla tıklandı ({res.get('method', 'InvokePattern')})."
        )
        return self._success(msg, data=res)


class WindowsSetControlText(BaseTool):
    """ValuePattern ile giriş/arama kutusuna metin yazar."""

    name = "windows_set_control_text"
    description = (
        "Set text in an input/edit/search control using IUIAutomation ValuePattern. "
        "Targets by AutomationId, Name, or ControlType without coordinate dependency."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta desteklenir.")

        params = self._params(tool_input)
        text_to_set = str(self._first_param(params, "text", "content", "value") or "")
        automation_id = str(self._first_param(params, "automation_id", "auto_id") or "").strip()
        element_name = str(self._first_param(params, "element_name", "element") or "").strip()
        window_title = self._first_param(params, "window_title", "window") or ""
        append_mode = bool(params.get("append_mode", False))

        if not text_to_set:
            return self._failure("text parametresi gerekli.")

        def _worker() -> dict[str, Any]:
            bridge = _get_bridge()
            if not bridge.available:
                return {"success": False, "error": "IUIAutomation COM arayüzü kullanılamıyor."}

            if window_title:
                root = bridge.find_window(str(window_title))
                if not root:
                    return {"success": False, "error": f"'{window_title}' penceresi bulunamadı."}
            else:
                root = bridge.find_foreground_window()
                if not root:
                    return {"success": False, "error": "Ön plan penceresi bulunamadı."}

            target = bridge.find_element_by(
                root,
                automation_id=automation_id,
                name=element_name,
                name_contains=element_name if not automation_id else "",
            )

            if not target:
                if pyautogui:
                    pyautogui.write(text_to_set)
                    return {
                        "success": True,
                        "window": window_title or "Ön plan",
                        "method": "pyautogui.write fallback",
                        "text_length": len(text_to_set),
                    }
                return {"success": False, "error": "Hedef eleman bulunamadı ve pyautogui kullanılamıyor."}

            final_text = text_to_set
            if append_mode:
                current = bridge.get_value(target)
                final_text = current + text_to_set

            success = bridge.set_value(target, final_text)

            try:
                win_name = root.CurrentName or ""
            except Exception:
                win_name = window_title or "Ön plan"

            return {
                "success": success,
                "window": win_name,
                "text_length": len(final_text),
                "method": "ValuePattern" if success else "WM_SETTEXT fallback",
            }

        res = await asyncio.to_thread(_worker)
        if not res.get("success"):
            return self._failure(str(res.get("error", "Metin girilemedi.")))

        return self._success(
            f"'{res['window']}' penceresine {res['text_length']} karakterlik metin "
            f"başarıyla girildi ({res.get('method', 'ValuePattern')}).",
            data=res,
        )


class WindowsGetElementTree(BaseTool):
    """Tam UIA ağaç yapısını JSON olarak döndürür — vision model bağlamı için."""

    name = "windows_get_element_tree"
    description = (
        "Get the full UIA element tree as structured JSON for vision model context. "
        "Includes hierarchy, AutomationId, ControlType, patterns, and bounding rects."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta desteklenir.")

        params = self._params(tool_input)
        window_title = self._first_param(params, "window_title", "window") or ""
        max_depth = int(self._first_param(params, "max_depth") or 3)
        max_elements = int(self._first_param(params, "max_elements") or 60)

        def _worker() -> dict[str, Any]:
            bridge = _get_bridge()
            if not bridge.available:
                return {"success": False, "error": "IUIAutomation COM arayüzü kullanılamıyor."}

            if window_title:
                root = bridge.find_window(str(window_title))
                if not root:
                    return {"success": False, "error": f"'{window_title}' penceresi bulunamadı."}
            else:
                root = bridge.find_foreground_window()
                if not root:
                    return {"success": False, "error": "Ön plan penceresi bulunamadı."}

            try:
                title = root.CurrentName or ""
            except Exception:
                title = ""

            elements = bridge.get_element_tree(root, max_depth=max_depth, max_elements=max_elements)

            interactive = [e for e in elements if e.get("supported_patterns")]
            non_interactive = [e for e in elements if not e.get("supported_patterns")]

            return {
                "success": True,
                "window_title": title,
                "total_elements": len(elements),
                "interactive_count": len(interactive),
                "interactive_elements": interactive[:40],
                "static_elements": non_interactive[:20],
            }

        res = await asyncio.to_thread(_worker)
        if not res.get("success"):
            return self._failure(str(res.get("error", "Ağaç yapısı alınamadı.")))

        summary = (
            f"'{res['window_title']}' penceresi: "
            f"{res['interactive_count']} etkileşimli / {res['total_elements']} toplam eleman."
        )
        return self._success(summary, data=res)
