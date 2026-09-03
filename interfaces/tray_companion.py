"""Windows Sistem Tepsisi Companion — Genişletilmiş menü ve sistem bilgisi.

Gelişmiş menü: ses.toggle, izin modu, GPU/VRAM, pil durumu, hızlı erişim.
"""

from __future__ import annotations

import os
import subprocess
import webbrowser
from typing import Any

from PIL import Image, ImageDraw

from config.logging import get_logger
from core.router import CognitiveRouter

logger = get_logger(__name__)


def _create_tray_icon(size: int = 64) -> Image.Image:
    """Siberpunk temalı neon OmniCore simgesi üretir."""
    from pathlib import Path

    logo_path = Path(__file__).resolve().parent.parent / "OmniCore-bounce.png"
    if logo_path.exists():
        try:
            img = Image.open(logo_path).convert("RGBA")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass

    img = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill="#0A0E17", outline="#00FFCC", width=3)
    draw.ellipse(
        [size // 4, size // 4, size * 3 // 4, size * 3 // 4],
        fill="#7C4DFF",
        outline="#FF007F",
        width=2,
    )
    center = size // 2
    draw.ellipse([center - 3, center - 3, center + 3, center + 3], fill="#FFFFFF")
    return img


class SystemTrayCompanion:
    """OmniCore Sistem Tepsisi Companion — gelişmiş menü ve telemetri."""

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router
        self._icon: Any | None = None
        self._running = False
        self._voice_active = False
        self._dashboard_url = "http://127.0.0.1:8000"

    def open_graph_rag(self) -> None:
        logger.info("tray.open_graph_rag")
        webbrowser.open(f"{self._dashboard_url}#view-graph")

    def get_telemetry_tooltip(self) -> str:
        """Genişletilmiş tooltip: CPU, RAM, GPU VRAM, pil, sağlayıcı."""
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            provider = getattr(self._router, "_runtime_provider", "gemini")
            model = getattr(self._router, "_runtime_model", "")

            lines = [
                "⚡ OmniCore Sovereign AI OS",
                f"🤖 {provider} — {model}",
                f"💻 CPU: {cpu}%",
                f"🧠 RAM: {ram.percent}% ({ram.used // (1024**2)}MB / {ram.total // (1024**2)}MB)",
            ]

            try:
                battery = psutil.sensors_battery()
                if battery:
                    plug = "⚡ Takılı" if battery.power_plugged else "🔋 Pilde"
                    lines.append(f"🔋 Pil: {battery.percent}% {plug}")
            except Exception:
                pass

            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3,
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_info = result.stdout.strip().split(", ")
                    if len(gpu_info) >= 4:
                        gpu_name = gpu_info[0]
                        vram_used = gpu_info[1]
                        vram_total = gpu_info[2]
                        temp = gpu_info[3]
                        lines.append(f"🎮 GPU: {gpu_name} ({vram_used}/{vram_total}MB) {temp}°C")
            except Exception:
                pass

            return "\n".join(lines)
        except Exception:
            return "OmniCore AI OS"

    def open_web_dashboard(self) -> None:
        logger.info("tray.open_dashboard")
        webbrowser.open(self._dashboard_url)

    def _toggle_voice(self) -> None:
        """Ses asistanını açar/kapatır."""
        self._voice_active = not self._voice_active
        state = "açık" if self._voice_active else "kapalı"
        logger.info("tray.voice_toggle", state=state)

    def _set_permission_mode(self, mode: str) -> None:
        """İzin modunu değiştirir."""
        try:
            from config.live_config import get_live_config
            get_live_config().set("approval_mode", mode)
            logger.info("tray.permission_changed", mode=mode)
        except Exception as exc:
            logger.error("tray.permission_failed", error=str(exc))

    def _open_folder(self, path: str) -> None:
        """Klasörü Dosya Yöneticisi'nde açar."""
        try:
            os.startfile(path)
        except Exception:
            subprocess.Popen(["explorer", path])

    def run(self) -> dict[str, Any]:
        """Sistem tepsisi ikonunu başlatır — genişletilmiş menü ile."""
        try:
            import pystray
        except ImportError:
            logger.warning("tray.pystray_not_installed")
            return {"status": "unavailable", "reason": "pystray not installed"}

        image = _create_tray_icon()

        def on_hover(icon: Any) -> None:
            try:
                icon.title = self.get_telemetry_tooltip()
            except Exception:
                pass

        menu = pystray.Menu(
            pystray.MenuItem("🖥️ Dashboard", lambda: self.open_web_dashboard()),
            pystray.MenuItem("📊 GraphRAG Aç", lambda: self.open_graph_rag()),
            pystray.MenuItem(
                "🔊 Ses Asistanı",
                lambda: self._toggle_voice(),
                checked=lambda item: self._voice_active,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "🔓 İzin Modu",
                pystray.Menu(
                    pystray.MenuItem("🟢 Tam Yetki (Full Auto)", lambda: self._set_permission_mode("yes")),
                    pystray.MenuItem("🟡 Güvenli (Safe)", lambda: self._set_permission_mode("safe")),
                    pystray.MenuItem("🔴 Sorarak (Ask)", lambda: self._set_permission_mode("ask")),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "📁 Hızlı Erişim",
                pystray.Menu(
                    pystray.MenuItem("🏠 Masaüstü", lambda: self._open_folder(os.path.expanduser("~/Desktop"))),
                    pystray.MenuItem("📥 İndirilenler", lambda: self._open_folder(os.path.expanduser("~/Downloads"))),
                    pystray.MenuItem("📁 Proje", lambda: self._open_folder(os.getcwd())),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Çıkış", lambda icon: icon.stop()),
        )

        self._icon = pystray.Icon(
            "OmniCore", image, "OmniCore Sovereign AI OS", menu=menu
        )
        self._running = True
        logger.info("tray.started")

        try:
            if hasattr(self._icon, "on_hover"):
                self._icon.on_hover = on_hover
        except Exception:
            pass

        self._icon.run()
        return {"status": "stopped"}

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
        self._running = False
