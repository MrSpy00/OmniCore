"""Windows Aktif Bağlam İzleyicisi — SetWinEventHook ile ön plan penceresini takip eder.

Kullanıcının o an hangi uygulamada olduğunu arka planda hafif bir Win32 hook ile takip edip
Bilişsel Yönlendiriciye sürekli bağlam sağlar.
"""

from __future__ import annotations

import ctypes
import threading
import time
from collections.abc import Callable
from typing import Any

try:
    import win32gui

    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

try:
    import psutil
except ImportError:
    psutil = None


EVENT_SYSTEM_FOREGROUND = 0x0003
WINEVENT_OUTOFCONTEXT = 0x0000


class ActiveContextObserver:
    """SetWinEventHook(EVENT_SYSTEM_FOREGROUND) ile ön plan penceresini izler.

    Her ön plan değişikliğinde pencere başlığını, işlem adını ve PID'yi önbelleğe kaydeder.
    Kayıtlı dinleyicilere geri çağırım ile bildirimde bulunur.
    """

    def __init__(self) -> None:
        self._hook_id: Any = None
        self._current_context: dict[str, Any] = {}
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        """Win32 event hook'unu yükler ve arka plan izlemeye başlar."""
        if self._running:
            return True
        if not _WIN32_AVAILABLE:
            return False

        try:
            self._running = True
            self._thread = threading.Thread(target=self._message_pump, daemon=True)
            self._thread.start()
            return True
        except Exception:
            self._running = False
            return False

    def stop(self) -> None:
        """İzlemeyi durdurur ve hook'u temizler."""
        self._running = False
        with self._lock:
            self._hook_id = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def on_foreground_change(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Ön plan değişikliğinde çağrılacak dinleyici ekler."""
        with self._lock:
            self._callbacks.append(callback)

    def get_current_context(self) -> dict[str, Any]:
        """Mevcut ön plan penceresi bağlamını döndürür."""
        with self._lock:
            return dict(self._current_context)

    def _message_pump(self) -> None:
        """Arka plan消息 pompası — hook callback'lerinin çalışması için gerekli."""
        if not _WIN32_AVAILABLE:
            return

        try:
            user32 = ctypes.windll.user32

            self._hook_id = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                0,
                WINEVENT_CALLBACK,
                0,
                0,
                WINEVENT_OUTOFCONTEXT,
            )

            if not self._hook_id:
                self._running = False
                return

            msg = ctypes.wintypes.MSG()
            while self._running:
                result = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if result == 0 or result == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except Exception:
            pass
        finally:
            if self._hook_id:
                try:
                    ctypes.windll.user32.UnhookWinEvent(self._hook_id)
                except Exception:
                    pass
            self._running = False

    def _on_event(self, hwnd: int) -> None:
        """Ön plan penceresi değiştiğinde çağrılır — bağlamı günceller."""
        if not hwnd or not _WIN32_AVAILABLE:
            return

        try:
            title = win32gui.GetWindowText(hwnd) if win32gui else ""
            if not title:
                return

            pid = 0
            try:
                _, pid = win32gui.GetWindowThreadProcessId(hwnd)
            except Exception:
                pass

            process_name = ""
            if psutil and pid:
                try:
                    proc = psutil.Process(pid)
                    process_name = proc.name()
                except Exception:
                    pass

            context = {
                "title": title,
                "hwnd": hwnd,
                "pid": pid,
                "process_name": process_name,
                "timestamp": time.time(),
            }

            with self._lock:
                self._current_context = context
                callbacks = list(self._callbacks)

            for cb in callbacks:
                try:
                    cb(context)
                except Exception:
                    pass

        except Exception:
            pass


# ─── Modül düzeyinde singleton ─────────────────────────────────────────────────────

_observer: ActiveContextObserver | None = None


def get_active_context_observer() -> ActiveContextObserver:
    global _observer
    if _observer is None:
        _observer = ActiveContextObserver()
    return _observer


def get_active_context() -> dict[str, Any] | None:
    """Mevcut aktif pencere bağlamını döndürür — router entegrasyonu için."""
    observer = get_active_context_observer()
    ctx = observer.get_current_context()
    return ctx if ctx else None


# ─── WINEVENT_CALLBACK ────────────────────────────────────────────────────────────

WINEVENT_CALLBACK = None

if _WIN32_AVAILABLE:
    try:
        _HANDLERFUNC = ctypes.WINFUNCTYPE(
            None,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.wintypes.HWND,
            ctypes.c_long,
            ctypes.c_long,
            ctypes.c_ulong,
            ctypes.c_ulong,
        )

        def _foreground_handler(event: int, hwnd: int, *_: Any) -> None:
            if event == EVENT_SYSTEM_FOREGROUND and hwnd:
                observer = get_active_context_observer()
                observer._on_event(hwnd)

        WINEVENT_CALLBACK = _HANDLERFUNC(_foreground_handler)
    except Exception:
        WINEVENT_CALLBACK = None
