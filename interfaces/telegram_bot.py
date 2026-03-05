"""Telegram Bot Gateway — primary async communication channel.

Uses ``python-telegram-bot`` v21+ with native asyncio support.  Handles:
  - Incoming user messages → forwarded to CognitiveRouter.
  - HITL approval requests → inline keyboard buttons.
  - Outgoing responses → sent back to the user.
"""

from __future__ import annotations

import asyncio
import html
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.logging import get_logger
from config.settings import get_settings
from core.guardian import ApprovalResult
from telegram.constants import ParseMode
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

# Pending HITL approval futures, keyed by a unique callback ID.
_pending_approvals: dict[str, asyncio.Future[ApprovalResult]] = {}


class TelegramGateway:
    """Async Telegram bot that bridges users to the CognitiveRouter.

    Parameters
    ----------
    router:
        The CognitiveRouter instance for processing messages.
    """

    def __init__(self, router: CognitiveRouter) -> None:
        self._router = router
        self._settings = get_settings()
        self._app: Application | None = None

    # -- lifecycle ------------------------------------------------------------

    def build(self) -> Application:
        """Build and configure the Telegram application."""
        builder = Application.builder().token(self._settings.telegram_bot_token)
        self._app = builder.build()

        # Register handlers.
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("clear", self._handle_clear))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self._app.add_handler(CallbackQueryHandler(self._handle_approval_callback))

        logger.info("telegram.built")
        return self._app

    async def run(self) -> None:
        """Start polling for updates. Blocks until shutdown."""
        if self._app is None:
            self.build()
        assert self._app is not None

        logger.info("telegram.starting_polling")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()  # type: ignore[union-attr]

        # Keep running until cancelled.
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully stop the bot."""
        if self._app:
            await self._app.updater.stop()  # type: ignore[union-attr]
            await self._app.stop()
            await self._app.shutdown()
        logger.info("telegram.shutdown")

    # -- auth helpers ----------------------------------------------------------

    def _is_allowed(self, user_id: int) -> bool:
        """Check if a user is in the allow list (empty = allow all)."""
        allowed = self._settings.allowed_user_ids
        return not allowed or user_id in allowed

    # -- command handlers ------------------------------------------------------

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_user and update.message
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("Unauthorized.", parse_mode="HTML")
            return
        await update.message.reply_text(
            "<b>OmniCore is online.</b>\n\n"
            "Send me a message and I'll help you with:\n"
            "- File management\n"
            "- Web searches and scraping\n"
            "- Shell commands (with approval)\n"
            "- External API calls\n\n"
            "Commands:\n"
            "<code>/status</code> — Show system status\n"
            "<code>/clear</code> — Clear conversation history",
            parse_mode=ParseMode.HTML,
        )

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_user and update.message
        if not self._is_allowed(update.effective_user.id):
            return
        provider = (self._settings.llm_provider or "gemini").strip().lower()
        if provider == "groq":
            model = self._settings.groq_llm_model
        else:
            provider = "gemini"
            model = self._settings.omni_llm_model
        provider = html.escape(provider)
        model = html.escape(model)
        await update.message.reply_text(
            "<b>OmniCore Status</b>\n"
            f"Provider: <code>{provider}</code>\n"
            f"Model: <code>{model}</code>\n"
            f"HITL Timeout: <code>{self._settings.hitl_timeout_minutes}m</code>",
            parse_mode=ParseMode.HTML,
        )

    async def _handle_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_user and update.message
        user_id = str(update.effective_user.id)
        if not self._is_allowed(update.effective_user.id):
            return
        self._router._short_term.clear(user_id)
        await update.message.reply_text(
            "Conversation history cleared.",
            parse_mode="HTML",
        )

    # -- message handler -------------------------------------------------------

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.effective_user and update.message and update.message.text
        user_id = update.effective_user.id
        if not self._is_allowed(user_id):
            await update.message.reply_text("Unauthorized.", parse_mode="HTML")
            return

        user_text = update.message.text
        logger.info("telegram.message", user_id=user_id, text=user_text[:100])

        # Show "typing" indicator while processing.
        await update.message.chat.send_action("typing")

        msg = Message(
            role=MessageRole.USER,
            content=user_text,
            channel="telegram",
            user_id=str(user_id),
        )

        try:
            reply = await self._router.handle_message(msg, conversation_id=str(user_id))
            # Telegram has a 4096-char limit per message.
            for chunk in _chunk_text(reply, 4096):
                await update.message.reply_text(_escape_html(chunk), parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.error("telegram.handler_error", error=str(exc))
            await update.message.reply_text(
                f"<b>Error:</b> {_escape_html(str(exc))}",
                parse_mode=ParseMode.HTML,
            )

    # -- HITL approval via inline keyboard ------------------------------------

    async def request_user_approval(self, action_description: str, user_id: str) -> ApprovalResult:
        """Send an inline keyboard to the user and wait for their response.

        This method is injected into the Guardian as the approval callback.
        """
        callback_id = f"hitl_{id(action_description)}_{user_id}"
        future: asyncio.Future[ApprovalResult] = asyncio.get_event_loop().create_future()
        _pending_approvals[callback_id] = future

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data=f"approve:{callback_id}"),
                    InlineKeyboardButton("Deny", callback_data=f"deny:{callback_id}"),
                ]
            ]
        )

        assert self._app
        await self._app.bot.send_message(
            chat_id=int(user_id),
            text=(
                "<b>APPROVAL REQUIRED</b>\n\n"
                f"Action: <code>{_escape_html(action_description)}</code>\n\n"
                f"This will time out in <code>{self._settings.hitl_timeout_minutes}</code> minutes."
            ),
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )

        try:
            result = await future
        finally:
            _pending_approvals.pop(callback_id, None)

        return result

    async def _handle_approval_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle inline keyboard button presses for HITL approvals."""
        query = update.callback_query
        assert query and query.data

        await query.answer()

        parts = query.data.split(":", 1)
        if len(parts) != 2:
            return

        action, callback_id = parts
        future = _pending_approvals.get(callback_id)
        if future is None or future.done():
            await query.edit_message_text(
                "This approval request has expired.",
                parse_mode=ParseMode.HTML,
            )
            return

        if action == "approve":
            future.set_result(ApprovalResult.APPROVED)
            await query.edit_message_text("Action APPROVED.", parse_mode=ParseMode.HTML)
        else:
            future.set_result(ApprovalResult.DENIED)
            await query.edit_message_text("Action DENIED.", parse_mode=ParseMode.HTML)


def _chunk_text(text: str, max_len: int) -> list[str]:
    """Split text into chunks of at most *max_len* characters."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks


def _escape_html(text: str) -> str:
    return html.escape(text, quote=False)
