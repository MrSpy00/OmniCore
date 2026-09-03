"""Local CLI gateway for development and testing.

Provides an interactive REPL with slash command menu (arrow-key navigation),
tab autocomplete, live config management, and clean error messages.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

# Force UTF-8 encoding across Windows console streams
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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


def _get_display_name() -> str:
    """Get the personalized user display name."""
    try:
        from config.live_config import get_live_config
        name = get_live_config().get("name")
        if name and name.strip():
            return name.strip()
    except Exception:
        pass
    try:
        settings = get_settings()
        if getattr(settings, "user_name", "") and settings.user_name.strip():
            return settings.user_name.strip()
    except Exception:
        pass
    import os, getpass
    try:
        return os.environ.get("OMNICORE_USER_NAME") or getpass.getuser() or "Operator"
    except Exception:
        return "Operator"


def _get_prompt_string() -> str:
    """Generate dynamic prompt string with user's name and styled chevron."""
    user = _get_display_name()
    return f"\n⚡ [{user}] ❯ "


# Commands that take arguments and should insert a trailing space on auto-completion
COMMANDS_REQUIRING_ARGS = {"/set", "/setmodel", "/provider", "/perm", "/name", "/plan", "/config"}

# All available slash commands with descriptions
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Yardım ve kullanım bilgisi"),
    ("/status", "Sistem durumu ve provider bilgisi"),
    ("/sysinfo", "Sistem bilgisi, CPU ve RAM donanım durumu"),
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

# High-contrast, crystal-clear dropdown styling — works on ANSI & TrueColor terminals
_PROMPT_STYLE = Style.from_dict({
    # Completion dropdown menu — high contrast for readability
    "completion-menu": "bg:#1a1f2e #e2e8f0",
    "completion-menu.completion": "bg:#1e293b #f8fafc",
    "completion-menu.completion.current": "bg:#0ea5e9 #ffffff bold",
    "completion-menu.meta.completion": "bg:#0f172a #cbd5e1",
    "completion-menu.meta.completion.current": "bg:#0ea5e9 #ffffff bold",
    "scrollbar.background": "bg:#0f172a",
    "scrollbar.button": "bg:#38bdf8",
})


if _HAS_PROMPT_TOOLKIT:
    class OmniCompleter(Completer):
        """Dropdown autocomplete completer for slash commands and subcommands."""

        def get_completions(self, document, complete_event):
            try:
                text = document.text_before_cursor
                if not text.startswith("/"):
                    return

                parts = text.split(maxsplit=1)
                cmd = parts[0].lower()

                # Main slash command completion
                if len(parts) == 1 and not text.endswith(" "):
                    for cmd_name, desc in SLASH_COMMANDS:
                        if cmd_name.startswith(cmd):
                            insert_text = f"{cmd_name} " if cmd_name in COMMANDS_REQUIRING_ARGS else cmd_name
                            yield Completion(
                                insert_text,
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
            except Exception:
                return
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

    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        try:
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
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


# Categorized slash commands for the interactive menu
_SLASH_CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    ("📊 Durum & Bilgi", [
        ("/status", "Sistem durumu"),
        ("/models", "Model listesi"),
        ("/sysinfo", "CPU/RAM bilgisi"),
        ("/doctor", "Teşhis aracı"),
    ]),
    ("⚙️ Ayarlar", [
        ("/setmodel", "Model değiştir"),
        ("/provider", "Provider değiştir"),
        ("/perm", "İzin modu"),
        ("/name", "Kullanıcı adı"),
        ("/set", "Hızlı ayar değiştir"),
        ("/config", "Detaylı ayarlar"),
        ("/plan", "Plan modu"),
    ]),
    ("🧠 Hafıza & İşlem", [
        ("/memory", "Bellek yönetimi"),
        ("/reset", "Oturumu sıfırla"),
        ("/commit", "Git commit"),
        ("/hud", "HUD göster"),
    ]),
    ("ℹ️ Yardım", [
        ("/help", "Kullanım kılavuzu"),
    ]),
]


def _interactive_slash_menu() -> str | None:
    """Show interactive arrow-key menu for slash commands.

    Returns the selected command string, or None if cancelled.
    On Windows: uses msvcrt for arrow keys with ANSI rendering if supported,
    otherwise falls back to numbered input menu.
    On Unix: uses tty/termios for arrow keys.
    """
    import os
    try:
        # Build flat list from categories
        flat_commands: list[tuple[str, str, str]] = []  # (cmd, desc, category)
        for cat_name, cmds in _SLASH_CATEGORIES:
            for cmd, desc in cmds:
                flat_commands.append((cmd, desc, cat_name))
        total = len(flat_commands)

        if os.name == "nt" and not _supports_ansi():
            return _show_slash_menu()

        idx = 0
        printed_lines = 0

        def _render():
            nonlocal printed_lines
            if printed_lines > 0:
                sys.stdout.write(f"\r\033[{printed_lines}A")
            lines = []
            lines.append("")
            lines.append("  \033[1;36m┌──────────────────────────────────────────────┐\033[0m")
            lines.append("  \033[1;36m│  📋 Komut Menüsü                             │\033[0m")
            lines.append("  \033[1;36m├──────────────────────────────────────────────┤\033[0m")

            flat_idx = 0
            for cat_name, cmds in _SLASH_CATEGORIES:
                lines.append(f"  \033[1;36m│\033[0m  \033[1;33m{cat_name}\033[0m")
                for cmd, desc in cmds:
                    if flat_idx == idx:
                        marker = "\033[1;46m \033[0m\033[1;97m ▸\033[0m"
                    else:
                        marker = "  "
                    lines.append(f"  \033[1;36m│\033[0m{marker} {cmd:<12} \033[90m{desc}\033[0m")
                    flat_idx += 1

            lines.append("  \033[1;36m├──────────────────────────────────────────────┤\033[0m")
            lines.append("  \033[1;36m│\033[0m  \033[90m↑↓:geçiş  Enter:seç  Esc:iptal  1-{n}:hızlı\033[0m".format(n=total))
            lines.append("  \033[1;36m└──────────────────────────────────────────────┘\033[0m")
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
                return flat_commands[idx][0]
            elif key == "ESC" or key == "CTRL_C":
                _cleanup()
                return None
            elif key and key.isdigit():
                num = int(key)
                if 1 <= num <= total:
                    idx = num - 1
                    _cleanup()
                    return flat_commands[idx][0]
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
        "                                ########    ######",
        "                              ##          ##      ##",
        "            ######            ########  ##          ##      ##  ########",
        "         ##      ##          ##        ##          ##      ##  ##      ##",
        "##      ##  ##      ##  ##      ##        ##        ##      ##  ##      ##  ##########",
        "    ##      ##  ####  ####  ####    ##        ##        ##      ##  ########    ##",
        "##      ##  ##  ##  ##  ##  ##  ##        ##  ########    ######    ##  ##      ##  ##",
        "  ##      ##  ##      ##  ##    ####        ##                  ##    ##    ########",
        "       ######    ##      ##  ##      ##  ##########                ##      ##  ##",
        "                   ##      ##  ##      ##                                ##",
        "               ##      ##  ##      ##                                ##########",
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
    lines.append(_bl("SOVEREIGN AUTONOMOUS AI OPERATING SYSTEM"))
    lines.append(_bb())
    username = _get_display_name()
    lines.append(_bl(f"{username} | {provider.upper()} | {model} | {perm_icon} | {sched_icon}"))
    lines.append(_bl(f"/ yaz -> komut menu  |  quit -> cikis"))
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

            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.filters import completion_is_selected

            kb = KeyBindings()

            @kb.add("/")
            def _(event):
                """Insert / and immediately show all slash commands."""
                buf = event.current_buffer
                buf.insert_text("/")
                try:
                    buf.start_completion()
                except Exception:
                    pass

            @kb.add("tab")
            def _(event):
                """Trigger completion on slash commands."""
                buf = event.current_buffer
                text = buf.text_before_cursor
                if text.startswith("/"):
                    if buf.complete_state:
                        buf.complete_next()
                    else:
                        try:
                            buf.start_completion(select_first=False)
                        except Exception:
                            pass
                else:
                    buf.insert_text("    ")

            @kb.add("enter")
            def _(event):
                """Apply selected completion or retain argument cursor for parameter-requiring commands."""
                buf = event.current_buffer
                if buf.complete_state and buf.complete_state.current_completion:
                    buf.apply_completion(buf.complete_state.current_completion)

                text = buf.text.strip()
                cmd_root = text.split()[0] if text else ""
                if cmd_root in COMMANDS_REQUIRING_ARGS and len(text.split()) <= 1:
                    try:
                        buf.cancel_completion()
                    except Exception:
                        pass
                    if not buf.text.endswith(" "):
                        buf.insert_text(" ")
                    return

                buf.validate_and_handle()

            self._prompt_session = PromptSession(
                completer=OmniCompleter(),
                complete_while_typing=False,
                style=_PROMPT_STYLE,
                key_bindings=kb,
                output=out,
            )

        except Exception as exc:
            logger.debug("cli.prompt_toolkit_init_error", error=str(exc))
            self._prompt_session = None

    def _on_step_progress(self, event_type: str, data: dict[str, Any]) -> None:
        """Display real-time step execution progress to the user."""
        if event_type == "thinking":
            text = data.get("text", "İstek analiz ediliyor...")
            sys.stdout.write(f"  🌀 \033[96m{text}\033[0m\n")
            sys.stdout.flush()

        elif event_type == "plan_created":
            total = data.get("total", 0)
            steps = data.get("steps", [])
            sys.stdout.write(f"\n  📋 \033[1;33m{total} Adımlık Plan Hazırlandı:\033[0m\n")
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
            bar = "█" * idx + "░" * (tot - idx)
            sys.stdout.write(f"\n  ⚡ \033[1;36m[{idx}/{tot}]\033[0m \033[1;37m{desc}\033[0m \033[90m({tool})\033[0m\n")
            sys.stdout.write(f"     \033[36m{bar}\033[0m\n")
            sys.stdout.flush()

        elif event_type == "step_end":
            idx = data.get("step", 1)
            tot = data.get("total", 1)
            status = data.get("status", "ok")
            res = str(data.get("result", ""))
            res_short = (res[:80] + "...") if len(res) > 80 else res
            if status in ("ok", "success"):
                sys.stdout.write(f"     └─ \033[92m✅\033[0m {res_short}\n")
            else:
                sys.stdout.write(f"     └─ \033[91m❌ {status}:\033[0m {res_short}\n")
            sys.stdout.flush()

        elif event_type == "summarizing":
            sys.stdout.write(f"  \033[36m▓▓▓▓▓▓▓▓▓▓\033[0m \033[95mSonuçlar toparlanıyor...\033[0m\n")
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
                    cmd_root = selected.strip().split()[0].lower()
                    if cmd_root in COMMANDS_REQUIRING_ARGS and len(selected.strip().split()) == 1:
                        hints = {
                            "/setmodel": "Model ID veya alias (örn: flash, pro, 20b, mixtral)",
                            "/perm": "Yetki modu (full | safe | ask)",
                            "/provider": "Sağlayıcı (gemini | groq | openai | anthropic | ollama)",
                            "/set": "Ayar ve değer (örn: approval_mode full, name mrSpy)",
                            "/config": "Alt komut (show | get <key> | set <key> <val>)",
                            "/plan": "on | off",
                        }
                        hint = hints.get(cmd_root, "Gerekli argümanlar")
                        print(f"\n💡 {cmd_root} — {hint}")
                        try:
                            arg_input = input(f"  {cmd_root} > ").strip()
                            if arg_input:
                                user_input = f"{cmd_root} {arg_input}"
                            else:
                                continue
                        except (KeyboardInterrupt, EOFError):
                            continue
                    else:
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

            # Intercept config and system info commands locally (not via router)
            first_word = user_input.strip().split()[0].lower() if user_input.strip() else ""
            if first_word in ("/config", "/set", "/perm", "/provider", "/setmodel", "/sysinfo", "/info"):
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
        prompt_str = _get_prompt_string()
        if self._prompt_session is not None:
            try:
                return self._prompt_session.prompt(prompt_str)
            except (KeyboardInterrupt, EOFError):
                return None
            except Exception:
                pass
        try:
            return input(prompt_str)
        except KeyboardInterrupt:
            return None
        except EOFError:
            raise

    def _print_sysinfo(self) -> None:
        """Display comprehensive local system and hardware information."""
        import platform
        import psutil
        live_config = get_live_config()
        settings = get_settings()
        provider = live_config.get("provider") or getattr(settings, "llm_provider", "groq")
        model = live_config.get("model") or getattr(settings, "groq_primary_model", "")
        approval = live_config.get("approval_mode") or getattr(settings, "approval_mode", "ask")
        tools_cnt = len(self._router._registry) if hasattr(self._router, "_registry") else 0

        cpu_pct = psutil.cpu_percent(interval=0.1)
        vm = psutil.virtual_memory()
        total_gb = vm.total / (1024 ** 3)
        used_gb = vm.used / (1024 ** 3)
        free_gb = vm.available / (1024 ** 3)

        print("\n" + "═" * 58)
        print("  💻 OMNICORE SİSTEM BİLGİSİ (SYSTEM INFO)")
        print("═" * 58)
        print(f"  👤 Kullanıcı Adı   : {_get_display_name()}")
        print(f"  🖥️  İşletim Sistemi : {platform.system()} {platform.release()} ({platform.machine()})")
        print(f"  🐍 Python Sürümü   : {platform.python_version()}")
        print(f"  🧠 Aktif LLM       : {provider} | {model}")
        print(f"  🛡️  Yetki Modu      : {approval.upper()}")
        print(f"  🔧 Araç Havuzu     : {tools_cnt} Otonom Araç")
        print("─" * 58)
        print(f"  ⚡ CPU Kullanımı   : %{cpu_pct}")
        print(f"  📊 Bellek (RAM)    : {used_gb:.1f} GB / {total_gb:.1f} GB (%{vm.percent}) [Boş: {free_gb:.1f} GB]")
        print("─" * 58)
        print("  🔒 Gizlilik Durumu : %100 YEREL (Cihaz dışına veri aktarılmaz)")
        print("═" * 58 + "\n")

    async def _handle_config_command(self, user_input: str) -> None:
        """Handle /config, /set, /perm, /provider, /setmodel, /sysinfo commands."""
        parts = user_input.strip().split(maxsplit=2)
        cmd = parts[0].lower()
        subcmd = parts[1].lower() if len(parts) > 1 else ""

        live_config = get_live_config()

        if cmd in ("/sysinfo", "/info"):
            self._print_sysinfo()
            return

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
                print("\n💡 Kullanım: /set <anahtar> <değer>")
                print("   Örnek: /set approval_mode full")
                print("   Örnek: /set name mrSpy")
                print("   Örnek: /set model openai/gpt-oss-20b")
                print("   Örnek: /set provider groq")
                print(f"\n📋 Mevcut Anahtarlar:\n   {', '.join(CONFIG_SCHEMA.keys())}\n")
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
                print("\n📋 İzin & Yetki Modu Seçin:")
                print("  [1] 🔓 full — Tam Yetki (tüm işlemler otomatik onaylanır, kalıcı)")
                print("  [2] 🔐 safe — Güvenli Mod (zararsız işlemler otomatik, kritik olanlar sorar)")
                print("  [3] 🔒 ask  — Sorarak Onay (her işlemde onay sorar)")
                try:
                    choice = input("\nSeçiminiz (1/2/3 veya full/safe/ask, Enter=iptal): ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    return
                choice_map = {"1": "full", "2": "safe", "3": "ask", "full": "full", "safe": "safe", "ask": "ask"}
                subcmd = choice_map.get(choice, "")
                if not subcmd:
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
                print(f"  📁 Kalici kayit: .env ({provider}_model = {resolved})")
                self._refresh_settings_on_router()

    def _refresh_settings_on_router(self) -> None:
        """Refresh the router's settings and rebuild LLM after config changes."""
        try:
            from config.settings import invalidate_settings_cache
            invalidate_settings_cache()
            new_settings = get_settings().model_copy(update=self._get_live_overrides())
            self._router._settings = new_settings
            self._router._destroy_current_llm()
            self._router._llm = self._router._build_llm(new_settings)
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
