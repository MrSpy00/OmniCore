"""Local CLI gateway for development and testing.

Provides a simple REPL that sends messages to the CognitiveRouter
without requiring Telegram credentials.
"""

from __future__ import annotations

import asyncio
import sys

from config.logging import get_logger
from core.guardian import ApprovalResult
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

_PROMPT = "\n[You] > "
_BANNER = """
+-------------------------------------+
|         OmniCore - CLI Mode         |
|  Type a message or 'quit' to exit.  |
|  Use .omnicore approve yes|ask.     |
+-------------------------------------+
"""


class CLIGateway:
    """Interactive terminal interface to OmniCore.

    HITL approvals are auto-approved in CLI mode (user is already at
    the keyboard).  Override by providing a custom approval callback.
    """

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router

    async def run(self) -> None:
        """Start the REPL loop."""
        print(_BANNER)
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
            if user_input.lower().startswith(".omnicore approve"):
                await self._handle_approval_toggle(user_input)
                continue
            if user_input.lower() == "/clear":
                self._router._short_term.clear(conversation_id)
                print("[System] Conversation cleared.")
                continue

            msg = Message(
                role=MessageRole.USER,
                content=user_input,
                channel="cli",
                user_id="cli_user",
            )

            try:
                print("\n[OmniCore] Thinking...")
                reply = await self._router.handle_message(msg, conversation_id)
                print(f"\n[OmniCore] {reply}")
            except Exception as exc:
                logger.error("cli.error", error=str(exc))
                print(f"\n[Error] {exc}")

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
