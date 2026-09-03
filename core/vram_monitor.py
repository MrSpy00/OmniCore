"""GPU VRAM İzleyici — Arka plan daemon olarak GPU VRAM basıncını izler.

Eşik değerleri aşıldığında otomatik olarak yerel LLM modellerini boşaltır
ve bulut sağlayıcılara geçiş yapar.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


_GAME_PROCESS_NAMES = {
    # Launchers & Platforms
    "steam.exe",
    "steamwebhelper.exe",
    "epicgameslauncher.exe",
    "galaxyclient.exe",
    "battle.net.exe",
    "riotclientservices.exe",
    # Anti-cheat
    "easyanticheat.exe",
    "easyanticheat_eos.exe",
    "battleye.exe",
    "beservice.exe",
    "vgtray.exe",
    "vgc.exe",
    # Common Games & Engines
    "valorant.exe",
    "cs2.exe",
    "csgo.exe",
    "dota2.exe",
    "leagueclient.exe",
    "leagueclientux.exe",
    "fortniteclient-win64-shipping.exe",
    "gta5.exe",
    "rdr2.exe",
    "cyberpunk2077.exe",
    "witcher3.exe",
    "apexlegends.exe",
    "pubg.exe",
    "overwatch.exe",
    "minecraft.exe",
    "javaw.exe",
    "unrealpak.exe",
    "ue4editor.exe",
    "ue5editor.exe",
    "unity.exe",
    "unityeditor.exe",
}


def detect_running_games() -> list[str]:
    """Detect running game or game engine processes via psutil."""
    try:
        import psutil

        active_games: list[str] = []
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in _GAME_PROCESS_NAMES:
                    active_games.append(name)
            except Exception:
                continue
        return sorted(list(set(active_games)))
    except Exception:
        return []


class VRAMMonitor:
    """GPU VRAM basıncını izler ve eşik aşıldığında otomatik tepki verir.

    Eşikler:
    - %85: Yüksek basınç → Ollama modellerini boşalt
    - %95: Kritik basınç → Acil durum, bulut geçişi
    """

    def __init__(
        self,
        poll_interval: float = 10.0,
        threshold_high: float = 0.85,
        threshold_critical: float = 0.95,
    ) -> None:
        self._poll_interval = poll_interval
        self._threshold_high = threshold_high
        self._threshold_critical = threshold_critical
        self._running = False
        self._game_running = False
        self._thread: threading.Thread | None = None
        self._last_status: dict[str, Any] = {}
        self._callbacks: list[callable] = []

    def start(self) -> bool:
        """Arka plan izlemeyi başlatır."""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("vram_monitor.started")
        return True

    def stop(self) -> None:
        """İzlemeyi durdurur."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def get_status(self) -> dict[str, Any]:
        """Mevcut VRAM durumunu döndürür."""
        if self._last_status:
            return dict(self._last_status)
        return self._query_gpu()

    def _poll_loop(self) -> None:
        """Periyodik VRAM ve oyun kontrol döngüsü."""
        while self._running:
            try:
                # 1. Game process detection and immediate suspension
                games = detect_running_games()
                if games and not self._game_running:
                    self._game_running = True
                    logger.warning("vram.game_detected_suspending_models", games=games)
                    self._unload_ollama_models()
                elif not games and self._game_running:
                    self._game_running = False
                    logger.info("vram.game_exited_restoring_models")

                # 2. VRAM GPU query
                status = self._query_gpu()
                status["active_games"] = games
                self._last_status = status

                vram_pct = status.get("vram_used_pct", 0)
                if vram_pct > self._threshold_critical:
                    logger.warning("vram.critical", usage=f"{vram_pct:.1%}")
                    self._unload_ollama_models()
                elif vram_pct > self._threshold_high:
                    logger.info("vram.high_pressure", usage=f"{vram_pct:.1%}")
                    self._unload_ollama_models()

                for cb in self._callbacks:
                    try:
                        cb(status)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(self._poll_interval)

    def _query_gpu(self) -> dict[str, Any]:
        """nvidia-smi ile GPU durumunu sorgular."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 5:
                    used = float(parts[1])
                    total = float(parts[2])
                    return {
                        "gpu_name": parts[0],
                        "vram_used_mb": used,
                        "vram_total_mb": total,
                        "vram_used_pct": used / total if total > 0 else 0,
                        "temperature": float(parts[3]),
                        "gpu_utilization": float(parts[4]),
                        "available": True,
                    }
        except Exception:
            pass
        return {"available": False}

    def _unload_ollama_models(self) -> bool:
        """Ollama API'sini kullanarak boşta olan modelleri boşaltır."""
        try:
            import httpx

            resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={"model": "", "keep_alive": 0},
                timeout=5,
            )
            if resp.status_code == 200:
                logger.info("vram.ollama_models_unloaded")
                return True
        except Exception:
            pass
        return False


_monitor: VRAMMonitor | None = None


def get_vram_monitor() -> VRAMMonitor:
    """Modül düzeyinde singleton VRAM monitörü."""
    global _monitor
    if _monitor is None:
        _monitor = VRAMMonitor()
    return _monitor
