"""Main entry point — boots all OmniCore subsystems.

Usage::

    uv run python scripts/run.py [--mode telegram|cli]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

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

# Ensure project root is on sys.path so all local packages resolve.
if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(sys._MEIPASS)
    _EXE_DIR = Path(sys.executable).resolve().parent
    if (_EXE_DIR / "tools").exists():
        _PROJECT_ROOT = _EXE_DIR
    elif (_EXE_DIR.parent / "tools").exists():
        _PROJECT_ROOT = _EXE_DIR.parent
    else:
        _PROJECT_ROOT = _BUNDLE_ROOT
    if str(_BUNDLE_ROOT) not in sys.path:
        sys.path.insert(0, str(_BUNDLE_ROOT))
else:
    _BUNDLE_ROOT = Path(__file__).resolve().parent.parent
    _PROJECT_ROOT = _BUNDLE_ROOT
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from config.logging import get_logger, setup_logging  # noqa: E402
from config.settings import get_settings  # noqa: E402
from core.router import CognitiveRouter  # noqa: E402
from memory.long_term import LongTermMemory  # noqa: E402
from memory.short_term import ShortTermMemory  # noqa: E402
from memory.state import StateTracker  # noqa: E402
from scheduler.pulse import AutonomousPulse  # noqa: E402
from tools.registry import ToolRegistry, discover_tool_classes  # noqa: E402
from tools.web_toolkit import shutdown_browser  # noqa: E402

os.chdir(os.path.expanduser("~"))

logger = get_logger(__name__)


def _build_tool_registry() -> ToolRegistry:
    """Discover and register all available tools dynamically."""
    registry = ToolRegistry()
    tools_dir = _BUNDLE_ROOT / "tools"
    if not tools_dir.exists():
        tools_dir = _PROJECT_ROOT / "tools"
    for tool_cls in discover_tool_classes(tools_dir):
        registry.register(tool_cls())
    return registry


async def _run(mode: str, debug: bool = False) -> None:
    # Set log level based on --debug flag.
    import logging as _logging

    log_level = _logging.DEBUG if debug else _logging.ERROR
    _logging.basicConfig(level=log_level)
    setup_logging()
    settings = get_settings()

    # Override ALL loggers to match debug flag.
    if not debug:
        _logging.getLogger().setLevel(_logging.ERROR)
        for name in _logging.Logger.manager.loggerDict:
            _logging.getLogger(name).setLevel(_logging.ERROR)

    logger.info("omnicore.starting", mode=mode, model=settings.omni_llm_model)

    # Validate required secrets — check only the active provider.
    provider = settings.llm_provider.strip().lower()
    availability = settings.provider_availability
    if provider not in ("ollama",) and not availability.get(provider, False):
        provider_env_map = {
            "groq": "GROQ_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }
        env_var = provider_env_map.get(provider, f"{provider.upper()}_API_KEY")
        logger.error("omnicore.missing_api_key", provider=provider)
        print(
            f"ERROR: {env_var} is not set for provider '{provider}'.\n"
            "Copy .env.example to .env and fill in your API key."
        )
        sys.exit(1)

    # Boot subsystems.
    short_term = ShortTermMemory()
    long_term = LongTermMemory()
    state_tracker = StateTracker()
    await state_tracker.initialize()

    tool_registry = _build_tool_registry()
    logger.info("omnicore.tools_registered", count=len(tool_registry))

    # Build the cognitive router (approval callback will be set by the gateway).
    router = CognitiveRouter(
        tool_registry=tool_registry,
        short_term=short_term,
        long_term=long_term,
        state_tracker=state_tracker,
        approval_callback=None,  # overridden below per gateway
    )

    # Apply persisted approval mode
    from config.live_config import get_live_config
    saved_approval = get_live_config().get("approval_mode") or getattr(settings, "approval_mode", "ask")
    router._guardian.set_mode(saved_approval)

    # Start the scheduler.
    pulse = AutonomousPulse(router, state_tracker)
    await pulse.start()

    try:
        # Select gateway.
        if mode == "telegram":
            if not settings.telegram_bot_token:
                logger.error("omnicore.missing_telegram_token")
                print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
                sys.exit(1)

            from interfaces.telegram_bot import TelegramGateway

            gateway = TelegramGateway(router)
            # Wire HITL approval callback.
            router._guardian._callback = gateway.request_user_approval
            logger.info("omnicore.gateway", type="telegram")
            await gateway.run()

        elif mode == "cli":
            from interfaces.cli import CLIGateway, cli_approval_callback

            router._guardian._callback = cli_approval_callback
            gateway = CLIGateway(router)
            logger.info("omnicore.gateway", type="cli")
            await gateway.run()

        elif mode == "rest":
            import uvicorn

            from interfaces.rest_api import create_app

            app = create_app(router)
            config = uvicorn.Config(app=app, host="0.0.0.0", port=8000, log_level="info")
            server = uvicorn.Server(config)
            logger.info("omnicore.gateway", type="rest", port=8000)
            await server.serve()

        elif mode == "web":
            import webbrowser

            import uvicorn

            from interfaces.dashboard import create_dashboard_app, set_router

            set_router(router)
            app = create_dashboard_app()
            config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, log_level="info")
            server = uvicorn.Server(config)
            logger.info("omnicore.gateway", type="web", port=8080)
            print("\n+==============================================================+")
            print("|  🚀 OmniCore Desktop Web GUI Başlatıldı!                     |")
            print("|  Tarayıcınız açılıyor: http://localhost:8080                  |")
            print("|  (CLI modunda çalıştırmak için: OmniCore.exe --mode cli)     |")
            print("+==============================================================+\n")

            def _auto_open_browser():
                try:
                    webbrowser.open("http://localhost:8080")
                except Exception:
                    pass

            asyncio.get_event_loop().call_later(1.0, _auto_open_browser)
            await server.serve()


        elif mode == "mcp":
            from interfaces.mcp_gateway import MCPServerGateway

            gateway = MCPServerGateway()
            logger.info("omnicore.gateway", type="mcp")
            print("[OmniCore MCP Gateway v0.40.0] Listening on stdio JSON-RPC 2.0...", flush=True)
            while True:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    break
                resp = await gateway.handle_request_json(line)
                print(resp, flush=True)

        elif mode == "hud":
            from interfaces.cli import CLIGateway, cli_approval_callback
            from interfaces.hud import generate_cyberpunk_hud_panel

            logger.info("omnicore.gateway", type="hud")
            print(
                generate_cyberpunk_hud_panel(
                    router_provider=getattr(settings, "llm_provider", "gemini"),
                    memory_nodes=0,
                    active_daemons=1,
                    tools_count=len(tool_registry),
                )
            )
            router._guardian._callback = cli_approval_callback
            gateway = CLIGateway(router)
            await gateway.run()

        elif mode == "voice":
            from interfaces.voice_duplex import VoiceEngine

            logger.info("omnicore.gateway", type="voice")
            voice = VoiceEngine(router)
            deps = voice.check_dependencies()
            missing = [k for k, v in deps.items() if not v]
            if missing:
                print(f"Voice deps missing: {', '.join(missing)}")
                print("Install: uv add SpeechRecognition sounddevice edge-tts")
                sys.exit(1)
            print("[OmniCore Voice] Dinlemeye hazir. Konusmaya baslayin.")
            print("[OmniCore Voice] Komutlar: 'quit' = cikis, 'kayit' = kayit bitir")
            try:
                while True:
                    try:
                        result = await asyncio.to_thread(
                            lambda: asyncio.run(voice.listen_and_respond())
                        )
                    except Exception:
                        # Run in main loop if thread fails
                        result = await voice.listen_and_respond()

                    if result.get("user_text"):
                        print(f"\n  [Siz] {result['user_text']}")
                        print(f"  [OmniCore] {result['response_text']}")
                    if result.get("response_audio"):
                        # Play audio if possible
                        try:
                            import tempfile
                            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                                f.write(result["response_audio"])
                                audio_path = f.name
                            # Try to play with system command
                            import subprocess
                            if sys.platform == "win32":
                                subprocess.Popen(
                                    ["start", "", audio_path],
                                    shell=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                            else:
                                subprocess.Popen(
                                    ["mpg123", audio_path],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                        except Exception:
                            pass
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\n[OmniCore Voice] Session ended.")

        else:
            print(f"Unknown mode: {mode}")
            sys.exit(1)
    finally:
        # Cleanup must run even on failures/cancellation.
        await pulse.stop()
        await shutdown_browser()
        await router.shutdown()
        await state_tracker.close()
        logger.info("omnicore.shutdown_complete")


def main() -> None:
    is_frozen = getattr(sys, "frozen", False)
    default_mode = "web" if is_frozen else "cli"

    parser = argparse.ArgumentParser(description="OmniCore AI OS Assistant v0.40.0")
    parser.add_argument(
        "--mode",
        choices=["cli", "telegram", "rest", "web", "mcp", "hud", "voice"],
        default=default_mode,
        help=f"Which gateway interface to launch (default: {default_mode})",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.mode, debug=args.debug))
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\nGoodbye.")
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
