"""Local CLI gateway for development and testing.

Provides an interactive REPL with slash command menu (arrow-key navigation),
tab autocomplete, live config management, and clean error messages.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

try:
    import readline
except ImportError:
    try:
        import pyreadline3 as readline  # type: ignore[no-redef]
    except ImportError:
        readline = None  # type: ignore[assignment]

try:
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit import PromptSession
    from prompt_toolkit.styles import Style
    from prompt_toolkit.output import create_output
    from prompt_toolkit.output.vt100 import Vt100_Output
    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    _HAS_PROMPT_TOOLKIT = False

from config.logging import get_logger
from config.live_config import get_live_config, CONFIG_SCHEMA, resolve_model_alias
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
    ("/provider", "Provider görüntüle/değiştir"),
    ("/config", "Yapılandırma ayarlarını göster/değiştir"),
    ("/set", "Hızlı ayar değiştir: /set <anahtar> <değer>"),
    ("/perm", "İzin modunu ayarla: /perm [full|safe|ask]"),
    ("/name", "Görünen adı değiştir: /name <yeni-isim>"),
    ("/plan", "Plan modunu aç/kapat: /plan [on|off]"),
    ("/doctor", "Sistem tanılaması"),
    ("/memory", "Uzun süreli bellek önizleme"),
    ("/reset", "Konuşma geçmişini temizle"),
    ("/hud", "Cyberpunk HUD göster"),
    ("/commit", "Git commit yardımcısı"),
]
SLASH_COMMAND_NAMES = [c[0] for c in SLASH_COMMANDS]

_PROMPT_STYLE = Style.from_dict({
    "completion-menu.completion": "bg:#202124 #e8eaed",
    "completion-menu.completion.current": "bg:#388bfd #ffffff bold",
    "completion-menu.meta.completion": "bg:#161618 #9aa0a6",
    "completion-menu.meta.completion.current": "bg:#388bfd #161618 bold",
    "scrollbar.background": "bg:#202124",
    "scrollbar.button": "bg:#5f6368",
})


if _HAS_PROMPT_TOOLKIT:
    class OmniCompleter(Completer):
        """Dropdown autocomplete completer for slash commands and subcommands."""

        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return

            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()

            # Main slash command completion
            if len(parts) == 1 and not text.endswith(" "):
                for cmd_name, desc in SLASH_COMMANDS:
                    if cmd_name.startswith(cmd):
                        yield Completion(
                            cmd_name,
                            start_position=-len(cmd),
                            display=cmd_name,
                            display_meta=desc,
                        )
                return

            # Subcommand completion
            sub_text = parts[1] if len(parts) > 1 else ""
            if cmd == "/perm":
                options = [
                    ("full", "🔓 Tam Yetki (tüm işlemler otomatik onaylanır, kalıcı)"),
                    ("safe", "🔐 Güvenli Mod (zararsız işlemler otomatik, kritik olanlar sorar)"),
                    ("ask", "🔒 Sorarak Onay (her işlemde onay sorar)"),
                ]
                for opt, desc in options:
                    if opt.startswith(sub_text.lower()):
                        yield Completion(
                            opt, start_position=-len(sub_text), display=opt, display_meta=desc
                        )

            elif cmd == "/provider":
                providers = [
                    ("gemini", "Google Gemini (2.5-flash / pro)"),
                    ("groq", "Groq (Llama-3.3-70b / Mixtral / Qwen)"),
                    ("openai", "OpenAI (GPT-4o / GPT-4.1)"),
                    ("anthropic", "Anthropic Claude"),
                    ("deepseek", "DeepSeek"),
                    ("mistral", "Mistral AI"),
                    ("ollama", "Yerel Offline LLM"),
                    ("auto", "Otomatik sağlayıcı geçişi"),
                ]
                for prov, desc in providers:
                    if prov.startswith(sub_text.lower()):
                        yield Completion(
                            prov, start_position=-len(sub_text), display=prov, display_meta=desc
                        )

            elif cmd == "/setmodel":
                aliases = [
                    ("flash", "gemini-2.5-flash (Google)"),
                    ("lite", "gemini-2.5-flash-lite (Google)"),
                    ("pro", "gemini-2.5-pro (Google)"),
                    ("20b", "openai/gpt-oss-20b (Groq)"),
                    ("120b", "openai/gpt-oss-120b (Groq)"),
                    ("mixtral", "mixtral-8x7b-32768 (Groq)"),
                    ("llama70b", "llama-3.3-70b-versatile (Groq)"),
                    ("llama8b", "llama-3.1-8b-instant (Groq)"),
                    ("deepseek", "deepseek-r1-distill-llama-70b (Groq)"),
                    ("qwen", "qwen-qwq-32b (Groq)"),
                ]
                for alias, desc in aliases:
                    if alias.startswith(sub_text.lower()):
                        yield Completion(
                            alias, start_position=-len(sub_text), display=alias, display_meta=desc
                        )

            elif cmd == "/plan":
                for opt, desc in [("on", "Plan modunu aç (dry-run zorunlu)"), ("off", "Plan modunu kapat")]:
                    if opt.startswith(sub_text.lower()):
                        yield Completion(
                            opt, start_position=-len(sub_text), display=opt, display_meta=desc
                        )

            elif cmd == "/config":
                for opt, desc in [
                    ("show", "Tüm yapılandırma ayarlarını göster"),
                    ("get", "Ayar oku: /config get <key>"),
                    ("set", "Ayar değiştir: /config set <key> <val>"),
                ]:
                    if opt.startswith(sub_text.lower()):
                        yield Completion(
                            opt, start_position=-len(sub_text), display=opt, display_meta=desc
                        )

            elif cmd == "/set":
                for opt, desc in [
                    ("model", "Aktif model"),
                    ("provider", "Aktif sağlayıcı"),
                    ("approval_mode", "Onay modu (full/safe/ask)"),
                    ("temperature", "LLM sıcaklığı (0.0-2.0)"),
                    ("name", "Görünen isim"),
                ]:
                    if opt.startswith(sub_text.lower()):
                        yield Completion(
                            opt, start_position=-len(sub_text), display=opt, display_meta=desc
                        )
else:
    class OmniCompleter:  # type: ignore[no-redef]
        pass


def _enable_ansi_windows() -> None:
    """Enable ANSI/VT escape code processing and UTF-8 encoding on Windows terminals."""
    import os

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Try stdout (STD_OUTPUT_HANDLE = -11)
        handle_out = kernel32.GetStdHandle(-11)
        mode_out = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle_out, ctypes.byref(mode_out)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            new_mode = mode_out.value | 0x0004
            kernel32.SetConsoleMode(handle_out, new_mode)
        # Also try stderr (STD_ERROR_HANDLE = -12)
        handle_err = kernel32.GetStdHandle(-12)
        mode_err = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle_err, ctypes.byref(mode_err)):
            kernel32.SetConsoleMode(handle_err, mode_err.value | 0x0004)
    except Exception:
        # Last resort: try via PowerShell
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "$p=[Console]::OutputEncoding; [Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
                 "$h=[IntPtr]-11; $m=[u]int32(0); "
                 "[Kernel32]::GetConsoleMode($h,[ref]$m) | Out-Null; "
                 "[Kernel32]::SetConsoleMode($h,$m -bor 4) | Out-Null"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass


_enable_ansi_windows()


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


def _read_key_windows() -> str | None:
    """Read a single keypress on Windows using msvcrt."""
    try:
        import msvcrt  # type: ignore[import-not-found]

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            # Extended key (arrow keys, function keys, etc.)
            ch2 = msvcrt.getwch()
            if ch2 == "H":
                return "UP"
            elif ch2 == "P":
                return "DOWN"
            elif ch2 == "K":
                return "LEFT"
            elif ch2 == "M":
                return "RIGHT"
            return None
        if ch == "\r":
            return "ENTER"
        if ch == "\x1b":
            return "ESC"
        if ch == "\x03":
            return "CTRL_C"
        return ch
    except Exception:
        return None


def _read_key_unix() -> str | None:
    """Read a single keypress on Unix/macOS."""
    import sys
    import tty
    import termios

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "UP"
                elif ch3 == "B":
                    return "DOWN"
                elif ch3 == "C":
                    return "RIGHT"
                elif ch3 == "D":
                    return "LEFT"
            return "ESC"
        if ch == "\r" or ch == "\n":
            return "ENTER"
        if ch == "\x03":
            return "CTRL_C"
        return ch
    except Exception:
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _read_key() -> str | None:
    """Read a single keypress, platform-aware."""
    import os
    if os.name == "nt":
        return _read_key_windows()
    return _read_key_unix()


def _supports_ansi() -> bool:
    """Check if the terminal supports ANSI escape codes."""
    import os
    if os.name != "nt":
        return True
    # Windows 10+ supports ANSI via VT processing
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        return bool(mode.value & 0x0004)
    except Exception:
        return False


def _interactive_slash_menu() -> str | None:
    """Show interactive arrow-key menu for slash commands.

    Returns the selected command string, or None if cancelled.
    On Windows: uses msvcrt for arrow keys with ANSI rendering if supported,
    otherwise falls back to numbered input menu.
    On Unix: uses tty/termios for arrow keys.
    """
    import os
    try:
        # On Windows, check if we can do arrow-key rendering
        if os.name == "nt" and not _supports_ansi():
            return _show_slash_menu()

        idx = 0
        total = len(SLASH_COMMANDS)
        printed_lines = 0

        def _render():
            nonlocal printed_lines
            # Move cursor up to overwrite previous render
            if printed_lines > 0:
                sys.stdout.write(f"\r\033[{printed_lines}A")
            lines = []
            lines.append("")
            lines.append("┌──────────────────────────────────────────────┐")
            lines.append("│  📋 Slash Komutları                          │")
            lines.append("├──────────────────────────────────────────────┤")
            for i, (cmd, desc) in enumerate(SLASH_COMMANDS):
                marker = " ▸ " if i == idx else "   "
                lines.append(f"│{marker}{cmd:<13} {desc:<24}│")
            lines.append("├──────────────────────────────────────────────┤")
            lines.append("│  ↑↓:geçiş  Enter:seç  Esc:iptal  1-9:hızlı  │")
            lines.append("└──────────────────────────────────────────────┘")
            output = "\n".join(lines)
            sys.stdout.write(output)
            sys.stdout.flush()
            printed_lines = len(lines)

        def _cleanup():
            nonlocal printed_lines
            if printed_lines > 0:
                sys.stdout.write(f"\r\033[{printed_lines}A")
                for _ in range(printed_lines):
                    sys.stdout.write("\033[2K\n")
                sys.stdout.flush()
                printed_lines = 0

        _render()

        while True:
            key = _read_key()
            if key is None:
                continue
            if key == "UP":
                idx = (idx - 1) % total
            elif key == "DOWN":
                idx = (idx + 1) % total
            elif key == "ENTER":
                _cleanup()
                return SLASH_COMMANDS[idx][0]
            elif key == "ESC" or key == "CTRL_C":
                _cleanup()
                return None
            elif key and key.isdigit():
                num = int(key)
                if 1 <= num <= total:
                    idx = num - 1
                    _cleanup()
                    return SLASH_COMMANDS[idx][0]
            elif key == "q":
                _cleanup()
                return None
            _render()
    except Exception:
        # Absolute fallback: simple numbered menu
        return _show_slash_menu()


def _get_banner() -> str:
    """Return a personalized CLI banner with ASCII art and status info."""
    settings = get_settings()
    live_config = get_live_config()
    provider = live_config.get("provider") or settings.llm_provider.strip().lower() or "gemini"
    model = live_config.get("model") or (
        settings.omni_llm_model if provider == "gemini" else settings.groq_primary_model
    )
    avail = settings.provider_availability
    key_ok = "✅" if avail.get(provider) else "❌"

    approval = live_config.get("approval_mode") or getattr(settings, "approval_mode", "ask")
    perm_icon = "🔓 FULL" if approval in ("yes", "full") else "🔐 SAFE" if approval == "safe" else "🔒 ASK"

    scheduler_on = live_config.get("scheduler") != "false"
    sched_icon = "SCHED:ON" if scheduler_on else "SCHED:OFF"

    W = 86  # box inner width

    art = [
        " #######  ##     ## ##    ## ####  ######   #######  ########  ######## ",
        "##     ## ###   ### ###   ##  ##  ##    ## ##     ## ##     ## ##       ",
        "##     ## #### #### ####  ##  ##  ##       ##     ## ##     ## ##       ",
        "##     ## ## ### ## ## ## ##  ##  ##       ##     ## ########  ######   ",
        "##     ## ##     ## ##  ####  ##  ##       ##     ## ##   ##   ##       ",
        "##     ## ##     ## ##   ###  ##  ##    ## ##     ## ##    ##  ##       ",
        " #######  ##     ## ##    ## ####  ######   #######  ##     ## ######## ",
    ]
    max_w = max(len(a) for a in art)
    margin = max(0, (W - max_w) // 2)

    def _bl(text: str = "") -> str:
        inner = text.center(W) if text else " " * W
        return f"|{inner}|"

    def _bb() -> str:
        return f"+{'=' * W}+"

    lines = [
        "",
        _bb(),
    ]
    for a in art:
        pad_r = W - margin - len(a)
        lines.append(f"|{' ' * margin}{a}{' ' * pad_r}|")
    lines.append(_bb())
    lines.append(_bl(f"{key_ok} {provider} | {model[:36]} | Yetki: {perm_icon} | {sched_icon}"))
    lines.append(_bl("💡 / yaz -> açılır komut menüsü  |  ↑↓ ile gezin  |  quit -> çıkış"))
    lines.append(_bb())

    return "\n".join(lines)


def _show_slash_menu() -> str | None:
    """Display slash command menu and accept numbered selection."""
    print("\n┌──────────────────────────────────────────────┐")
    print("│  📋 Slash Komutları                          │")
    print("├──────────────────────────────────────────────┤")
    for i, (cmd, desc) in enumerate(SLASH_COMMANDS, 1):
        num = f"[{i:2d}]" if i <= 9 else f"[{i}]"
        line = f"│  {num} {cmd:<13} {desc:<24}│"
        print(line)
    print("├──────────────────────────────────────────────┤")
    print("│  Numara girin veya komutu yazın (Enter=iptal)│")
    print("└──────────────────────────────────────────────┘")
    try:
        choice = input("  > ").strip()
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(SLASH_COMMANDS):
                return SLASH_COMMANDS[num - 1][0]
        # Also accept direct command input
        if choice.startswith("/"):
            return choice
    except (KeyboardInterrupt, EOFError):
        pass
    return None


def _clean_error(exc: Exception) -> str:
    """Convert raw exceptions to user-friendly messages."""
    msg = str(exc)
    if "API key not valid" in msg or "API_KEY_INVALID" in msg:
        return "❌ API anahtarınız geçersiz. /config ile ayarları kontrol edin."
    if "not valid" in msg.lower() and "api key" in msg.lower():
        return "❌ API anahtarınız geçersiz. /config ile ayarları kontrol edin."
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
    # Generic fallback
    return f"⚠️ Bir hata oluştu: {type(exc).__name__}"


class CLIGateway:
    """Interactive terminal interface to OmniCore.

    HITL approvals are auto-approved in CLI mode (user is already at
    the keyboard).  Override by providing a custom approval callback.
    """

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router
        self._prompt_session: Any = None
        self._init_prompt_session()

    def _init_prompt_session(self) -> None:
        """Initialize prompt_toolkit PromptSession with dropdown autocompletion."""
        if not _HAS_PROMPT_TOOLKIT:
            self._prompt_session = None
            return
        try:
            import shutil
            try:
                out = create_output()
            except Exception:
                out = Vt100_Output(
                    sys.stdout,
                    lambda: (shutil.get_terminal_size().lines, shutil.get_terminal_size().columns),
                )

            self._prompt_session = PromptSession(
                completer=OmniCompleter(),
                complete_while_typing=True,
                style=_PROMPT_STYLE,
                output=out,
            )
        except Exception as exc:
            logger.debug("cli.prompt_toolkit_init_error", error=str(exc))
            self._prompt_session = None

    def _on_step_progress(self, event_type: str, data: dict[str, Any]) -> None:
        """Display real-time step execution progress to the user."""
        if event_type == "thinking":
            text = data.get("text", "İstek analiz ediliyor...")
            sys.stdout.write(f"\r\033[K  🌀 \033[96m{text}\033[0m\n")
            sys.stdout.flush()

        elif event_type == "plan_created":
            total = data.get("total", 0)
            steps = data.get("steps", [])
            sys.stdout.write(f"  📋 \033[1;33m{total} Adımlı Plan Hazırlandı:\033[0m\n")
            for s in steps:
                s_idx = s.get("step", 1)
                s_desc = s.get("description", "")
                s_tool = s.get("tool", "")
                sys.stdout.write(f"     \033[90m{s_idx}.\033[0m {s_desc} \033[90m({s_tool})\033[0m\n")
            sys.stdout.flush()

        elif event_type == "step_start":
            idx = data.get("step", 1)
            tot = data.get("total", 1)
            tool = data.get("tool", "")
            desc = data.get("description", "")
            sys.stdout.write(f"\n  ⚡ \033[1;36m[{idx}/{tot}]\033[0m {desc} \033[90m({tool})\033[0m...\n")
            sys.stdout.flush()

        elif event_type == "step_end":
            idx = data.get("step", 1)
            tot = data.get("total", 1)
            status = data.get("status", "ok")
            res = str(data.get("result", ""))
            res_short = (res[:90] + "...") if len(res) > 90 else res
            if status in ("ok", "success"):
                sys.stdout.write(f"     └─ \033[92m✅ Başarılı:\033[0m {res_short}\n")
            else:
                sys.stdout.write(f"     └─ \033[91m❌ Durum:\033[0m {res_short}\n")
            sys.stdout.flush()

        elif event_type == "summarizing":
            sys.stdout.write("  ✨ \033[95mSonuçlar toparlanıyor...\033[0m\n")
            sys.stdout.flush()

    async def run(self) -> None:
        """Start the REPL loop."""
        _enable_ansi_windows()
        _setup_autocomplete()
        print(_get_banner())
        print("  Bir mesaj yaz veya / ile komutlari gor\n")
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
                print("\n\nGörüşürüz! 👋")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            # Exit commands
            if user_input.lower() in ("quit", "exit", "q", "çık", "cik"):
                print("Görüşürüz! 👋")
                break

            # Show interactive slash menu when user types just "/"
            if user_input == "/":
                selected = await asyncio.to_thread(_interactive_slash_menu)
                if selected:
                    user_input = selected
                else:
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

            # Handle new config/permission commands locally (not via router)
            if user_input.lower().startswith(("/config", "/set ", "/perm", "/provider", "/setmodel")):
                await self._handle_config_command(user_input)
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
                reply = await self._router.handle_message(
                    msg, conversation_id, on_progress=self._on_step_progress
                )
                print(f"\n{reply}")
            except Exception as exc:
                logger.error("cli.error", error=str(exc))
                print(f"\n{_clean_error(exc)}")

    def _safe_input(self) -> str | None:
        """Run prompt_toolkit prompt or standard input() and return None on KeyboardInterrupt."""
        if self._prompt_session is not None:
            try:
                return self._prompt_session.prompt(_PROMPT)
            except (KeyboardInterrupt, EOFError):
                return None
            except Exception:
                pass
        try:
            return input(_PROMPT)
        except KeyboardInterrupt:
            return None
        except EOFError:
            raise

    async def _handle_config_command(self, user_input: str) -> None:
        """Handle /config, /set, /perm, /provider, /setmodel commands."""
        parts = user_input.strip().split(maxsplit=2)
        cmd = parts[0].lower()
        subcmd = parts[1].lower() if len(parts) > 1 else ""

        live_config = get_live_config()

        if cmd == "/config":
            if subcmd == "set" and len(parts) >= 3:
                key_value = parts[2].strip().split(maxsplit=1)
                if len(key_value) < 2:
                    print("Kullanım: /config set <anahtar> <değer>")
                    return
                key, value = key_value
                success, msg = live_config.set(key.strip(), value.strip())
                print(f"\n{msg}")
                if success:
                    self._refresh_settings_on_router()
            elif subcmd == "get" and len(parts) >= 3:
                key = parts[2].strip()
                schema = CONFIG_SCHEMA.get(key)
                if not schema:
                    print(f"Geçersiz anahtar: {key}")
                    return
                env_var = schema.get("env_var")
                if env_var:
                    current = live_config.get_env_value(env_var) or "(varsayılan)"
                    print(f"\n  {key} = {current}  ({schema['description']})")
                else:
                    print(f"\n  {key} = (runtime only)")
            else:
                # Show all config
                print(f"\n{live_config.show()}")

        elif cmd == "/set":
            if len(parts) < 3:
                print("Kullanım: /set <anahtar> <değer>")
                print(f"Mevcut anahtarlar: {', '.join(CONFIG_SCHEMA.keys())}")
                return
            key = parts[1].strip()
            value = parts[2].strip()

            # Handle model aliases
            if key == "model":
                provider = live_config.get("provider") or "gemini"
                value = resolve_model_alias(value, provider)

            success, msg = live_config.set(key, value)
            print(f"\n{msg}")
            if success:
                self._refresh_settings_on_router()

        elif cmd == "/perm":
            if not subcmd or subcmd not in ("full", "safe", "ask"):
                print(
                    "\nKullanım: /perm <mod>\n\n"
                    "Modlar:\n"
                    "  full  — Tüm işlemler otomatik onaylanır (kalıcı, onay sormaz)\n"
                    "  safe  — Güvenli mod (zararsız işlemler otomatik, tehlikeliler sorar)\n"
                    "  ask   — Her işlemde onay sorar (varsayılan)"
                )
                return
            mode_map = {"full": "yes", "safe": "safe", "ask": "ask"}
            mode = mode_map[subcmd]
            success, msg = live_config.set("approval_mode", mode)
            if success:
                self._router._guardian.set_mode(mode)
                perm_names = {
                    "full": "🔓 Tam Yetki (Otomatik onay, kalıcı)",
                    "safe": "🔐 Güvenli Mod (Zararsızlar otomatik, kritik işlemler sorar)",
                    "ask": "🔒 Sorarak Onay (Her işlemde onay sorar)",
                }
                print(f"\n✅ İzin modu güncellendi ve kaydedildi: {perm_names.get(subcmd, subcmd)}")
            else:
                print(f"\n❌ {msg}")

        elif cmd == "/provider":
            if not subcmd:
                current = live_config.get("provider") or get_settings().llm_provider
                print(f"\nAktif Sağlayıcı: {current}")
                print("Değiştirmek için: /provider <gemini|groq|openai|anthropic|deepseek|mistral|ollama|auto>")
                return
            success, msg = live_config.set("provider", subcmd)
            print(f"\n{msg}")
            if success:
                self._refresh_settings_on_router()

        elif cmd == "/setmodel":
            if not subcmd:
                provider = live_config.get("provider") or get_settings().llm_provider
                current = live_config.get("model") or "varsayılan"
                print(f"\nAktif Model: {current} (Provider: {provider})")
                print("Değiştirmek için: /setmodel <model-id veya alias>")
                return
            provider = live_config.get("provider") or get_settings().llm_provider
            resolved = resolve_model_alias(subcmd, provider)
            success, msg = live_config.set_model_for_provider(provider, resolved)
            print(f"\n{msg}")
            if success:
                self._refresh_settings_on_router()

    def _refresh_settings_on_router(self) -> None:
        """Refresh the router's settings after config changes."""
        try:
            # Force re-read by updating the router's internal settings reference
            self._router._settings = get_settings().model_copy(
                update=self._get_live_overrides()
            )
        except Exception:
            pass

    def _get_live_overrides(self) -> dict[str, Any]:
        """Collect current live config values as a settings override dict."""
        live_config = get_live_config()
        overrides: dict[str, Any] = {}
        if live_config.get("model"):
            overrides["omni_llm_model"] = live_config.get("model")
        if live_config.get("provider"):
            overrides["llm_provider"] = live_config.get("provider")
        if live_config.get("name") is not None:
            overrides["user_name"] = live_config.get("name") or ""
        if live_config.get("temperature"):
            overrides["llm_temperature"] = float(live_config.get("temperature"))
        if live_config.get("max_tokens"):
            overrides["llm_max_output_tokens"] = int(live_config.get("max_tokens"))
        return overrides

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
    print(f"\n┌──────────────────────────────────────────────┐")
    print(f"│  ⚠️  ONAY GEREKLİ                           │")
    print(f"├──────────────────────────────────────────────┤")
    # Wrap long descriptions
    desc_lines = []
    words = action_description.split()
    current_line = "  "
    for word in words:
        if len(current_line) + len(word) + 1 > 42:
            desc_lines.append(current_line)
            current_line = "  " + word
        else:
            current_line += " " + word if current_line.strip() else "  " + word
    if current_line.strip():
        desc_lines.append(current_line)
    for line in desc_lines[:5]:
        print(f"│{line:<46}│")
    print(f"├──────────────────────────────────────────────┤")
    print(f"│  Onaylıyor musunuz? (e/h)                    │")
    print(f"└──────────────────────────────────────────────┘")

    def _ask() -> str:
        try:
            return input("  > ")
        except KeyboardInterrupt:
            return "h"

    response = await asyncio.to_thread(_ask)
    if response.strip().lower() in ("e", "y", "evet", "yes"):
        print("  ✅ Onaylandı\n")
        return ApprovalResult.APPROVED
    print("  ❌ Reddedildi\n")
    return ApprovalResult.DENIED


def _write_to_stderr(msg: str) -> None:
    """Write to stderr without buffering issues."""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
