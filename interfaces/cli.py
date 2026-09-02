"""Local CLI gateway for development and testing.

Provides an interactive REPL with slash command menu (arrow-key navigation),
tab autocomplete, and clean error messages.
"""

from __future__ import annotations

import asyncio
import sys

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline  # type: ignore[no-redef]
    except ImportError:
        readline = None  # type: ignore[assignment]

from config.logging import get_logger
from config.settings import get_settings
from core.guardian import ApprovalResult
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

_PROMPT = "\n[You] > "

# All available slash commands with descriptions
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Yardım ve kullanım bilgisi"),
    ("/status", "Sistem durumu ve provider bilgisi"),
    ("/models", "Kullanılabilir modeller ve API key durumu"),
    ("/setmodel", "Model değiştir: /setmodel <model-id>"),
    ("/provider", "Provider görüntüle/değiştir: /provider [gemini|groq|openai|...]"),
    ("/name", "Görünen adı değiştir: /name <yeni-isim>"),
    ("/plan", "Plan modunu aç/kapat: /plan [on|off]"),
    ("/doctor", "Sistem tanılaması"),
    ("/memory", "Uzun süreli bellek önizleme"),
    ("/reset", "Konuşma geçmişini temizle"),
    ("/hud", "Cyberpunk HUD göster"),
    ("/commit", "Git commit yardımcısı"),
]
SLASH_COMMAND_NAMES = [c[0] for c in SLASH_COMMANDS]


def _setup_autocomplete() -> None:
    """Configure readline for slash command autocomplete."""
    if readline is None:
        return

    def completer(text: str, state: int) -> str | None:
        if not text.startswith("/"):
            return None
        matches = [c for c in SLASH_COMMAND_NAMES if c.startswith(text)]
        if state < len(matches):
            return matches[state]
        return None

    readline.set_completer(completer)
    readline.set_completer_delims(" \t\n")
    readline.parse_and_bind("tab: complete")


def _get_banner() -> str:
    """Return a personalized CLI banner."""
    settings = get_settings()
    display_name = settings.user_name.strip() or settings.system_name
    provider = settings.llm_provider.strip().lower() or "gemini"
    model = settings.omni_llm_model if provider == "gemini" else settings.groq_primary_model
    avail = settings.provider_availability
    key_ok = "✅" if avail.get(provider) else "❌"

    # Pad name to make banner look good
    title_line = f"  {display_name} - CLI Modu"
    return (
        "\n"
        "╔══════════════════════════════════════════╗\n"
        f"║{title_line:<44}║\n"
        "║  Mesaj yaz veya 'quit' ile çık           ║\n"
        "║  / yazıp Tab → komut tamamlama           ║\n"
        f"║  {key_ok} {provider} | {model[:30]:<30}║\n"
        "╚══════════════════════════════════════════╝\n"
    )


def _show_slash_menu() -> None:
    """Display slash command menu in a formatted box."""
    print("\n┌─────────────────────────────────────────────┐")
    print("│  📋 Slash Komutları (Tab ile tamamla)       │")
    print("├─────────────────────────────────────────────┤")
    for cmd, desc in SLASH_COMMANDS:
        line = f"│  {cmd:<12} {desc:<31}│"
        print(line)
    print("└─────────────────────────────────────────────┘")
    print("  Kullanım: komut yazıp Enter'a bas\n")


def _clean_error(exc: Exception) -> str:
    """Convert raw exceptions to user-friendly messages."""
    msg = str(exc)
    if "API key not valid" in msg or "API_KEY_INVALID" in msg:
        return "❌ API anahtarınız geçersiz. .env dosyasında API key'i kontrol edin."
    if "not valid" in msg.lower() and "api key" in msg.lower():
        return "❌ API anahtarınız geçersiz. .env dosyasında API key'i kontrol edin."
    if "429" in msg or "rate limit" in msg.lower():
        return "⏳ Çok fazla istek gönderildi. Biraz bekleyin ve tekrar deneyin."
    if "413" in msg or "payload too large" in msg.lower():
        return "📏 Mesajınız çok uzun. Daha kısa bir şekilde ifade edin."
    if "timeout" in msg.lower() or "DeadlineExceeded" in msg:
        return "⏱️ Sunucu zaman aşımı. Ağ bağlantınızı kontrol edin."
    if "UNAUTHENTICATED" in msg:
        return "🔒 Kimlik doğrulama başarısız. API key'i kontrol edin."
    if "not found" in msg.lower() and "model" in msg.lower():
        return "🔍 Model bulunamadı. /models ile mevcut modelleri kontrol edin."
    if "no longer available" in msg.lower():
        return "⚠️ Bu model artık mevcut değil. /models yazarak güncel modeli seçin."
    if "connection" in msg.lower() or "connect" in msg.lower():
        return "🌐 Ağ bağlantısı kurulamıyor. İnternet bağlantınızı kontrol edin."
    # Generic fallback — hide internal details in non-debug mode
    return f"⚠️ Bir hata oluştu: {type(exc).__name__}"


class CLIGateway:
    """Interactive terminal interface to OmniCore.

    HITL approvals are auto-approved in CLI mode (user is already at
    the keyboard).  Override by providing a custom approval callback.
    """

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router

    async def run(self) -> None:
        """Start the REPL loop."""
        _setup_autocomplete()
        print(_get_banner())
        print("  💡 Bir mesaj yazın veya / ile komutları görün\n")
        conversation_id = "cli_session"

        while True:
            try:
                user_input = await asyncio.to_thread(self._safe_input)
            except (EOFError, KeyboardInterrupt):
                print("\n\nGörüşürüz! 👋")
                break
            except asyncio.CancelledError:
                print("\n\nGörüşürüz! 👋")
                break

            if user_input is None:
                # Ctrl+C caught in safe_input
                print("\n\nGörüşürüz! 👋")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # Exit commands
            if user_input.lower() in ("quit", "exit", "q", "çık", "cik"):
                print("Görüşürüz! 👋")
                break

            # Show slash menu when user types just "/"
            if user_input == "/":
                _show_slash_menu()
                continue

            # /hud special case
            if user_input.lower() == "/hud":
                from interfaces.hud import generate_cyberpunk_hud_panel

                tools_cnt = (
                    len(self._router._registry) if hasattr(self._router, "_registry") else 40
                )
                mem_nodes = getattr(self._router._long_term, "count", lambda: 0)()
                print(generate_cyberpunk_hud_panel(tools_count=tools_cnt, memory_nodes=mem_nodes))
                continue

            # Slash commands
            if user_input.startswith("/"):
                msg = Message(
                    role=MessageRole.USER,
                    content=user_input,
                    channel="cli",
                    user_id="cli_user",
                )
                try:
                    reply = await self._router.handle_message(msg, conversation_id)
                    print(f"\n{reply}")
                except Exception as exc:
                    logger.error("cli.error", error=str(exc))
                    print(f"\n{_clean_error(exc)}")
                continue

            # .omnicore approve toggle
            if user_input.lower().startswith(".omnicore approve"):
                await self._handle_approval_toggle(user_input)
                continue

            # Regular message
            msg = Message(
                role=MessageRole.USER,
                content=user_input,
                channel="cli",
                user_id="cli_user",
            )

            try:
                settings = get_settings()
                display_name = settings.user_name.strip() or settings.system_name
                print(f"\n[{display_name}] Düşünüyor...")
                reply = await self._router.handle_message(msg, conversation_id)
                print(f"\n{reply}")
            except Exception as exc:
                logger.error("cli.error", error=str(exc))
                print(f"\n{_clean_error(exc)}")

    def _safe_input(self) -> str | None:
        """Run input() and return None on KeyboardInterrupt (Ctrl+C)."""
        try:
            return input(_PROMPT)
        except KeyboardInterrupt:
            return None
        except EOFError:
            raise

    async def _handle_approval_toggle(self, user_input: str) -> None:
        parts = user_input.strip().split()
        if len(parts) < 3:
            print("[System] Kullanım: .omnicore approve [yes|ask]")
            return
        mode = parts[2].strip().lower()
        if mode not in ("yes", "ask"):
            print("[System] Geçersiz mod. 'yes' veya 'ask' kullanın.")
            return
        applied = self._router._guardian.set_mode(mode)
        print(f"[System] Onay modu ayarlandı: {applied.value}")


async def cli_approval_callback(action_description: str, user_id: str) -> ApprovalResult:
    """Prompt the user for approval in the terminal."""
    print(f"\n[ONAY GEREKLİ] {action_description}")

    def _ask() -> str:
        try:
            return input("Onaylıyor musunuz? (e/h): ")
        except KeyboardInterrupt:
            return "h"

    response = await asyncio.to_thread(_ask)
    if response.strip().lower() in ("e", "y", "evet", "yes"):
        return ApprovalResult.APPROVED
    return ApprovalResult.DENIED


def _write_to_stderr(msg: str) -> None:
    """Write to stderr without buffering issues."""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
