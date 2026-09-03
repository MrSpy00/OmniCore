"""OmniCore Spotlight — Yarı saydam GUI overlay komut çubuğu.

Terminal REPL yerine CustomTkinter tabanlı siberpunk temalı GUI overlay.
Global Ctrl+Space kısayolu ile açılır/kapatılır.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import Any

from config.logging import get_logger
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

try:
    import customtkinter as ctk

    _CTK_AVAILABLE = True
except ImportError:
    _CTK_AVAILABLE = False


class SpotlightBar:
    """Spotlight / Raycast-style anlık komut çalıştırma barı."""

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router
        self._conversation_id = "spotlight_session"

    async def execute_query(self, query: str) -> dict[str, Any]:
        clean_q = query.strip()
        if not clean_q:
            return {"status": "empty", "reply": ""}

        logger.info("spotlight.execute", query=clean_q[:80])
        msg = Message(
            role=MessageRole.USER,
            content=clean_q,
            channel="spotlight",
            user_id="spotlight_user",
        )

        try:
            reply = await self._router.handle_message(msg, self._conversation_id)
            return {"status": "success", "query": clean_q, "reply": reply}
        except Exception as exc:
            logger.error("spotlight.failed", error=str(exc))
            return {"status": "error", "query": clean_q, "reply": f"Hata: {exc}"}


class SpotlightOverlay:
    """Siberpunk temalı yarı saydam komut çubuğu overlay'i.

    CustomTkinter kullanarak ekranın ortasında cyan/purple neon kenarlıklı
    bir komut çubuğu oluşturur. Escape veya kısayol tuşu ile kapatılır.
    """

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router
        self._bar = SpotlightBar(router)
        self._root: Any = None
        self._backdrop: Any = None
        self._entry: Any = None
        self._result_box: Any = None
        self._status_label: Any = None
        self._visible = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._history: list[str] = []
        self._history_idx = -1

    def _apply_cyberpunk_theme(self) -> None:
        """Siberpunk tema uygular — koyu arka plan, cyan/purple neon."""
        if not _CTK_AVAILABLE or not self._root:
            return
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self._root.configure(fg_color="#0A0E17")
        self._root.attributes("-alpha", 0.94)
        self._root.attributes("-topmost", True)

    def show(self) -> None:
        """Overlay'i ekranın ortasında gösterir ve odaklanır."""
        if not _CTK_AVAILABLE:
            logger.warning("spotlight.ctk_not_available")
            return

        from pathlib import Path

        from PIL import Image

        if self._visible and self._root:
            if self._backdrop:
                self._backdrop.deiconify()
                self._backdrop.lift()
            self._root.deiconify()
            self._root.lift()
            self._root.focus_force()
            if self._entry:
                self._entry.focus_set()
            return

        self._root = ctk.CTk()
        self._root.title("OmniCore Spotlight")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.94)

        screen_w = self._root.winfo_screenwidth()
        screen_h = self._root.winfo_screenheight()

        # Dimmed backdrop overlay
        try:
            self._backdrop = ctk.CTkToplevel(self._root)
            self._backdrop.overrideredirect(True)
            self._backdrop.geometry(f"{screen_w}x{screen_h}+0+0")
            self._backdrop.configure(fg_color="#020408")
            self._backdrop.attributes("-alpha", 0.45)
            self._backdrop.attributes("-topmost", True)
            self._backdrop.bind("<Button-1>", lambda e: self.hide())
        except Exception:
            self._backdrop = None

        width = 740
        height = 340
        x = (screen_w - width) // 2
        y = (screen_h - height) // 3
        self._root.geometry(f"{width}x{height}+{x}+{y}")

        self._apply_cyberpunk_theme()

        container = ctk.CTkFrame(
            self._root, fg_color="#0A0E17",
            corner_radius=16, border_color="#7C4DFF", border_width=2,
        )
        container.pack(fill="both", expand=True, padx=4, pady=4)

        # Header Frame with Logo
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(10, 4))

        logo_path = Path(__file__).resolve().parent.parent / "OmniCore-bounce.png"
        logo_img = None
        if logo_path.exists():
            try:
                pil_img = Image.open(logo_path).convert("RGBA")
                logo_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(28, 28))
            except Exception:
                pass

        if logo_img:
            header = ctk.CTkLabel(
                header_frame,
                image=logo_img,
                compound="left",
                text="  OMNICORE SPOTLIGHT",
                font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
                text_color="#00FFCC",
            )
        else:
            header = ctk.CTkLabel(
                header_frame,
                text="⚡ OMNICORE SPOTLIGHT",
                font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
                text_color="#00FFCC",
            )
        header.pack(side="left")

        esc_hint = ctk.CTkLabel(
            header_frame,
            text="ESC ile kapat",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#64748B",
        )
        esc_hint.pack(side="right")

        self._entry = ctk.CTkEntry(
            container,
            placeholder_text="Komutunuzu yazın... (Örn: 'spotify'dan müzik aç', 'ekrana bak')",
            font=ctk.CTkFont(family="Consolas", size=14),
            fg_color="#111827",
            border_color="#00FFCC",
            border_width=1,
            text_color="#F8FAFC",
            placeholder_text_color="#64748B",
            height=44,
        )
        self._entry.pack(fill="x", padx=16, pady=(4, 6))
        self._entry.bind("<Return>", self._on_submit)
        self._entry.bind("<Escape>", lambda e: self.hide())
        self._entry.bind("<Up>", self._on_history_prev)
        self._entry.bind("<Down>", self._on_history_next)

        self._status_label = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#64748B",
        )
        self._status_label.pack(anchor="w", padx=16, pady=(0, 2))

        # Rich Markdown / Code Result Output Box
        self._result_box = ctk.CTkTextbox(
            container,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#070A10",
            border_color="#1E293B",
            border_width=1,
            text_color="#E2E8F0",
            wrap="word",
            height=180,
        )
        self._result_box.pack(fill="both", expand=True, padx=16, pady=(2, 10))

        self._root.after(100, lambda: self._entry.focus_set())
        self._visible = True

        self._root.mainloop()

    def hide(self) -> None:
        """Overlay'i ve backdrop'u gizler."""
        if self._root:
            self._root.withdraw()
        if self._backdrop:
            self._backdrop.withdraw()
        self._visible = False

    def toggle(self) -> None:
        """Görünürlüğü değiştirir."""
        if self._visible:
            self.hide()
        else:
            self.show()

    def _on_history_prev(self, _event: Any = None) -> None:
        """Önceki komutu geçmişten getirir."""
        if not self._history or not self._entry:
            return
        if self._history_idx == -1:
            self._history_idx = len(self._history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        cmd = self._history[self._history_idx]
        self._entry.delete(0, "end")
        self._entry.insert(0, cmd)

    def _on_history_next(self, _event: Any = None) -> None:
        """Sonraki komutu geçmişten getirir."""
        if not self._history or not self._entry:
            return
        if self._history_idx < len(self._history) - 1 and self._history_idx != -1:
            self._history_idx += 1
            cmd = self._history[self._history_idx]
            self._entry.delete(0, "end")
            self._entry.insert(0, cmd)
        else:
            self._history_idx = -1
            self._entry.delete(0, "end")

    def _on_submit(self, _event: Any = None) -> None:
        """Enter tuşuna basıldığında komutu çalıştırır."""
        if not self._entry:
            return
        query = self._entry.get().strip()
        if not query:
            return

        if query not in self._history:
            self._history.append(query)
        self._history_idx = -1

        if self._status_label:
            self._status_label.configure(text_color="#FF007F", text="⏳ İşleniyor...")
        if self._result_box:
            self._result_box.delete("1.0", "end")
            self._result_box.insert("1.0", "OmniCore düşünüyor...\n")

        def _do_query() -> None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(self._bar.execute_query(query))
                reply = result.get("reply", "")
                self._root.after(0, lambda: self._show_result(reply))
                loop.close()
            except Exception as _exc:
                self._root.after(0, lambda e=str(_exc): self._show_result(f"Hata: {e}"))

        thread = threading.Thread(target=_do_query, daemon=True)
        thread.start()

    def _show_result(self, text: str) -> None:
        """Sonucu result_box'a yazar."""
        if self._status_label:
            self._status_label.configure(text_color="#00FFCC", text="✓ Tamamlandı")
        if self._result_box:
            self._result_box.delete("1.0", "end")
            self._result_box.insert("1.0", text)


async def run_spotlight_gui(router: CognitiveRouter) -> None:
    """GUI Spotlight overlay'ini başlatır (terminal REPL yerine)."""
    overlay = SpotlightOverlay(router)

    try:
        from interfaces.spotlight_hotkey import register_global_hotkey

        def toggle_overlay() -> None:
            if overlay._root:
                overlay._root.after(0, overlay.toggle)

        register_global_hotkey(toggle_overlay)
    except Exception:
        pass

    await asyncio.to_thread(overlay.show)


async def run_spotlight_interactive(router: CognitiveRouter) -> None:
    """Terminal Spotlight REPL'i — GUI mevcut olmadığında fallback."""
    if _CTK_AVAILABLE and sys.platform == "win32":
        await run_spotlight_gui(router)
        return

    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import HTML

    spotlight = SpotlightBar(router)
    session: PromptSession[str] = PromptSession()

    print("\n" + "=" * 55)
    print(" ⚡ OMNICORE SPOTLIGHT — Hızlı Komut Barı (Çıkış: q/exit)")
    print("=" * 55 + "\n")

    while True:
        try:
            query = await session.prompt_async(HTML("<ansicyan><b>OmniCore ❯ </b></ansicyan>"))
            query = query.strip()
            if not query:
                continue
            if query.lower() in ("q", "exit", "quit"):
                break

            result = await spotlight.execute_query(query)
            print(f"\n{result['reply']}\n")
        except (KeyboardInterrupt, EOFError):
            break
