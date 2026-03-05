"""Main entry point — boots all OmniCore subsystems.

Usage::

    uv run python scripts/run.py [--mode telegram|cli]
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

# Ensure project root is on sys.path so all local packages resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.logging import setup_logging, get_logger
from config.settings import get_settings
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.state import StateTracker
from tools.registry import ToolRegistry
from tools.os_toolkit import (
    OsReadFile,
    OsWriteFile,
    OsListDir,
    OsMoveFile,
    OsDeleteFile,
    OsSystemInfo,
)
from tools.terminal_toolkit import TerminalExecute
from tools.web_toolkit import WebNavigate, WebSearch, WebScreenshot, shutdown_browser
from tools.advanced_web_toolkit import WebExtractLinks, WebReadArticle
from tools.api_toolkit import ApiHttpRequest, ApiWeather, ApiDatetime
from tools.advanced_os_toolkit import (
    OsResourceMonitor,
    OsListRunningProcesses,
    OsKillProcess,
    OsClipboardRead,
    OsClipboardWrite,
)
from tools.media_toolkit import MediaDownloadYoutubeAudio, MediaGetYoutubeTranscript
from tools.network_toolkit import NetPing, NetGetIP
from core.router import CognitiveRouter
from scheduler.pulse import AutonomousPulse


logger = get_logger(__name__)


def _build_tool_registry() -> ToolRegistry:
    """Register all available tools."""
    registry = ToolRegistry()
    for tool_cls in [
        # OS toolkit
        OsReadFile,
        OsWriteFile,
        OsListDir,
        OsMoveFile,
        OsDeleteFile,
        OsSystemInfo,
        # Terminal
        TerminalExecute,
        # Web
        WebNavigate,
        WebSearch,
        WebScreenshot,
        WebExtractLinks,
        WebReadArticle,
        # API
        ApiHttpRequest,
        ApiWeather,
        ApiDatetime,
        # Advanced OS
        OsResourceMonitor,
        OsListRunningProcesses,
        OsKillProcess,
        OsClipboardRead,
        OsClipboardWrite,
        # Media
        MediaDownloadYoutubeAudio,
        MediaGetYoutubeTranscript,
        # Network
        NetPing,
        NetGetIP,
    ]:
        registry.register(tool_cls())
    return registry


async def _run(mode: str) -> None:
    setup_logging()
    settings = get_settings()

    logger.info("omnicore.starting", mode=mode, model=settings.omni_llm_model)

    # Validate required secrets.
    if settings.llm_provider.strip().lower() == "groq":
        if not settings.groq_api_key:
            logger.error("omnicore.missing_groq_api_key")
            print("ERROR: GROQ_API_KEY is not set. Copy .env.example to .env and fill it in.")
            sys.exit(1)
    else:
        if not settings.google_api_key:
            logger.error("omnicore.missing_google_api_key")
            print("ERROR: GOOGLE_API_KEY is not set. Copy .env.example to .env and fill it in.")
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

    # Start the scheduler.
    pulse = AutonomousPulse(router, state_tracker)
    await pulse.start()

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

    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

    # Cleanup.
    await pulse.stop()
    await shutdown_browser()
    await state_tracker.close()
    logger.info("omnicore.shutdown_complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="OmniCore AI Assistant")
    parser.add_argument(
        "--mode",
        choices=["telegram", "cli"],
        default="cli",
        help="Which gateway interface to launch (default: cli)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.mode))


if __name__ == "__main__":
    main()
