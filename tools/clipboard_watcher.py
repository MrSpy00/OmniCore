"""Arka Plan Pano İzleyicisi Daemon — Windows clipboard viewer chain kullanarak
pano değişimlerini izler ve içerik türünü otomatik olarak sınıflandırır.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from config.logging import get_logger
from tools.smart_clipboard_toolkit import _detect_content_type

logger = get_logger(__name__)

try:
    import pyperclip

    _CLIPBOARD_AVAILABLE = True
except ImportError:
    _CLIPBOARD_AVAILABLE = False


class ClipboardWatcher:
    """Arka plan pano izleyicisi — hata izi, JSON, SQL, URL algılama.

    Windows'ta periyodik olarak pano içeriğini kontrol eder ve
    değişim olduğunda kayıtlı dinleyicileri bilgilendirir.
    """

    def __init__(self, poll_interval: float = 1.0, max_history: int = 50) -> None:
        self._poll_interval = poll_interval
        self._max_history = max_history
        self._history: list[dict[str, Any]] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: list[Callable[[dict[str, Any]], None]] = []
        self._last_content: str = ""
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Arka plan izlemeyi başlatır."""
        if self._running:
            return True
        if not _CLIPBOARD_AVAILABLE:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info("clipboard_watcher.started")
        return True

    def stop(self) -> None:
        """İzlemeyi durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def on_change(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Pano değişiminde çağrılacak dinleyici ekler."""
        self._callbacks.append(callback)

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Son pano değişim geçmişini döndürür."""
        with self._lock:
            return list(reversed(self._history[-limit:]))

    def get_latest(self) -> dict[str, Any] | None:
        """En son pano girişini döndürür."""
        with self._lock:
            return self._history[-1] if self._history else None

    def _watch_loop(self) -> None:
        """Periyodik pano izleme döngüsü."""
        while self._running:
            try:
                content = pyperclip.paste()
                if content and content != self._last_content:
                    self._last_content = content
                    content_type = _detect_content_type(content)

                    cat = content_type.get("category", "text")
                    typ = content_type.get("type", "plain_text")

                    suggestion = ""
                    if cat == "error":
                        suggestion = f"Hata algılandı: {content_type.get('error_summary', 'Traceback')}"
                    elif typ == "json":
                        suggestion = "JSON verisi kopyalandı."
                    elif typ == "sql_query":
                        suggestion = "SQL sorgusu kopyalandı."
                    elif typ == "url":
                        suggestion = f"URL kopyalandı: {content_type.get('url')}"

                    entry = {
                        "timestamp": time.time(),
                        "content_preview": content[:200],
                        "content_length": len(content),
                        "content_type": content_type,
                        "suggestion": suggestion,
                        "text": content[:5000],
                    }

                    with self._lock:
                        self._history.append(entry)
                        if len(self._history) > self._max_history:
                            self._history = self._history[-self._max_history:]

                    for cb in self._callbacks:
                        try:
                            cb(entry)
                        except Exception:
                            pass

                    if cat not in ("plain_text", "unknown", "text"):
                        logger.info(
                            "clipboard_watcher.detected",
                            category=cat,
                            type=typ,
                            length=len(content),
                        )
            except Exception:
                pass
            time.sleep(self._poll_interval)


_watcher: ClipboardWatcher | None = None


def get_clipboard_watcher() -> ClipboardWatcher:
    """Modül düzeyinde singleton pano izleyicisi."""
    global _watcher
    if _watcher is None:
        _watcher = ClipboardWatcher()
    return _watcher
