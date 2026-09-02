"""Local CLI gateway for development and testing.

Provides an interactive REPL with slash command autocomplete,
arrow-key navigation, and clean error messages.
"""

from __future__ import annotations

import asyncio

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None  # type: ignore[assignment]

from config.logging import get_logger
from config.settings import get_settings
from core.guardian import ApprovalResult
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

_PROMPT = "\n[You] > "

# All available slash commands
SLASH_COMMANDS = [
    "/help", "/status", "/name", "/provider", "/setmodel",
    "/models", "/plan", "/doctor", "/memory", "/reset",
    "/hud", "/commit",
]


def _setup_autocomplete() -> None:
    """Configure readline for slash command autocomplete."""
    if readline is None:
        return

    def completer(text: str, state: int) -> str | None:
        if not text.startswith("/"):
            return None
        matches = [c for c in SLASH_COMMANDS if c.startswith(text)]
        if state < len(matches):
            return matches[state]
        return None

    readline.set_completer(completer)
    readline.set_completer_delims(" \t\n")
    readline.parse_and_bind("tab: complete")


def _get_banner() -> str:
    """Return a personalized CLI banner."""
    settings = get_settings()
    name = settings.user_name.strip() or "OmniCore"
    provider = settings.llm_provider.strip().lower() or "gemini"
    model = settings.omni_llm_model if provider == "gemini" else settings.groq_primary_model
    return f"""
+-------------------------------------+
|     {name} - CLI Mode              |
|  Type a message or 'quit' to exit.  |
|  Type / for commands, Tab to auto.  |
|  Provider: {provider} | Model: {model[:25]} |
+-------------------------------------+
"""


def _clean_error(exc: Exception) -> str:
    """Convert raw exceptions to user-friendly messages."""
    msg = str(exc)
    if "API key not valid" in msg or "API_KEY_INVALID" in msg:
        return "API anahtariniz gecersiz. .env dosyasinda API key'i kontrol edin."
    if "429" in msg or "rate limit" in msg.lower():
        return "Cok fazla istek gonderildi. Biraz bekleyin ve tekrar deneyin."
    if "413" in msg or "payload too large" in msg.lower():
        return "Mesajiniz cok uzun. Daha kisa bir sekilde ifade edin."
    if "timeout" in msg.lower() or "DeadlineExceeded" in msg:
        return "Sunucu zaman asimi. Ag baglantinizi kontrol edin."
    if "UNAUTHENTICATED" in msg:
        return "Kimlik dogrulama basarisiz. API key'i kontrol edin."
    if "not found" in msg.lower() and "model" in msg.lower():
        return "Model bulunamadi. /models ile mevcut modelleri kontrol edin."
    if "connection" in msg.lower() or "connect" in msg.lower():
        return "Ag baglantisi kurulamiyor. Internet baglantinizi kontrol edin."
    # Generic fallback — hide internal details
    return f"Bir hata olustu: {type(exc).__name__}"


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
        conversation_id = "cli_session"

        while True:
            try:
                user_input = await asyncio.to_thread(input, _PROMPT)
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break
            if user_input.lower() == "/hud":
                from interfaces.hud import generate_cyberpunk_hud_panel

                tools_cnt = (
                    len(self._router._registry)
                    if hasattr(self._router, "_registry")
                    else 40
                )
                mem_nodes = getattr(self._router._long_term, "count", lambda: 0)()
                print(generate_cyberpunk_hud_panel(tools_count=tools_cnt, memory_nodes=mem_nodes))
                continue
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
            if user_input.lower().startswith(".omnicore approve"):
                await self._handle_approval_toggle(user_input)
                continue

            msg = Message(
                role=MessageRole.USER,
                content=user_input,
                channel="cli",
                user_id="cli_user",
            )

            try:
                print("\nThinking...")
                reply = await self._router.handle_message(msg, conversation_id)
                print(f"\n{reply}")
            except Exception as exc:
                logger.error("cli.error", error=str(exc))
                print(f"\n{_clean_error(exc)}")

    async def _handle_approval_toggle(self, user_input: str) -> None:
        parts = user_input.strip().split()
        if len(parts) < 3:
            print("[System] Usage: .omnicore approve [yes|ask]")
            return
        mode = parts[2].strip().lower()
        if mode not in ("yes", "ask"):
            print("[System] Invalid mode. Use 'yes' or 'ask'.")
            return
        applied = self._router._guardian.set_mode(mode)
        print(f"[System] Approval mode set to: {applied.value}")


async def cli_approval_callback(action_description: str, user_id: str) -> ApprovalResult:
    """Prompt the user for approval in the terminal."""
    print(f"\n[APPROVAL REQUIRED] {action_description}")
    response = await asyncio.to_thread(input, "Approve? (y/n): ")
    if response.strip().lower() in ("y", "yes"):
        return ApprovalResult.APPROVED
    return ApprovalResult.DENIED
