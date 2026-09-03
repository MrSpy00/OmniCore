"""Windows Ses Olayları İzleyicisi — Sistem ses oturumlarını izler.

pycaw IAudioSessionManager2 kullanarak sistem ses olaylarını (yeni ses oturumu,
durum değişikliği, ses seviyesi) dinler ve tepki verir.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


class AudioSessionMonitor:
    """Windows ses oturumlarını izler — pycaw ile.”

    Yeni bir uygulama ses çalmaya başladığında veya durduğunda
    tetiklenecek geri çağırma fonksiyonları kaydedilebilir.
    """

    def __init__(self, poll_interval: float = 2.0) -> None:
        self._poll_interval = poll_interval
        self._callbacks: list[Callable[[list[dict[str, Any]]], None]] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_sessions: dict[int, dict[str, Any]] = {}

    def start(self) -> bool:
        """Arka plan izlemeyi başlatır."""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("audio_monitor.started")
        return True

    def stop(self) -> None:
        """İzlemeyi durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def on_session_change(self, callback: Callable[[list[dict[str, Any]]], None]) -> None:
        """Ses oturumu değişikliğinde çağrılacak dinleyici ekler."""
        self._callbacks.append(callback)

    def get_active_sessions(self) -> list[dict[str, Any]]:
        """Mevcut aktif ses oturumlarını döndürür."""
        if not _PSUTIL_AVAILABLE:
            return []
        return self._scan_audio_processes()

    def _monitor_loop(self) -> None:
        """Arka plan izleme döngüsü."""
        while self._running:
            try:
                current = self._scan_audio_processes()
                current_pids = {s["pid"] for s in current}

                new_sessions = [
                    s for s in current if s["pid"] not in self._last_sessions
                ]
                ended_pids = [
                    pid for pid in self._last_sessions
                    if pid not in current_pids
                ]

                if new_sessions or ended_pids:
                    for cb in self._callbacks:
                        try:
                            cb(current)
                        except Exception:
                            pass

                self._last_sessions = {s["pid"]: s for s in current}
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def _scan_audio_processes(self) -> list[dict[str, Any]]:
        """Ses kullanan süreçleri tarar."""
        if not _PSUTIL_AVAILABLE:
            return []

        audio_keywords = [
            "chrome", "firefox", "edge", "spotify", "discord", "vlc",
            "zoom", "teams", "skype", "obs", "audacity", "media",
        ]

        sessions: list[dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                if any(kw in name for kw in audio_keywords):
                    sessions.append({
                        "pid": info["pid"],
                        "name": info.get("name", ""),
                        "status": info.get("status", ""),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return sessions
