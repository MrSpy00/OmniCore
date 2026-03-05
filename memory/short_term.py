"""Short-term memory: sliding-window conversation buffer.

Keeps the most recent *N* messages per conversation so the LLM context
window is not exceeded.  Older messages are evicted but can still be
retrieved from long-term memory (ChromaDB).
"""

from __future__ import annotations

from collections import defaultdict

from config.logging import get_logger
from models.messages import Conversation, Message

logger = get_logger(__name__)

# Default maximum number of messages retained per conversation.
_DEFAULT_MAX_MESSAGES = 50


class ShortTermMemory:
    """In-memory sliding-window buffer for active conversations.

    Parameters
    ----------
    max_messages:
        Maximum number of messages to keep per conversation.  When this
        limit is exceeded the oldest messages are silently dropped.
    """

    def __init__(self, max_messages: int = _DEFAULT_MAX_MESSAGES) -> None:
        self._max = max_messages
        self._conversations: dict[str, Conversation] = defaultdict(Conversation)

    # -- public API -----------------------------------------------------------

    def add_message(self, conversation_id: str, message: Message) -> None:
        """Append *message* to the conversation, evicting old ones if full."""
        conv = self._conversations[conversation_id]
        conv.add(message)
        if len(conv.messages) > self._max:
            evicted = len(conv.messages) - self._max
            conv.messages = conv.messages[evicted:]
            logger.debug(
                "short_term.evicted",
                conversation_id=conversation_id,
                evicted=evicted,
            )

    def get_conversation(self, conversation_id: str) -> Conversation:
        """Return the current conversation buffer (may be empty)."""
        return self._conversations[conversation_id]

    def get_recent_messages(self, conversation_id: str, n: int | None = None) -> list[Message]:
        """Return the last *n* messages (default: all retained)."""
        msgs = self._conversations[conversation_id].messages
        if n is None:
            return list(msgs)
        return list(msgs[-n:])

    def clear(self, conversation_id: str) -> None:
        """Wipe a conversation buffer entirely."""
        self._conversations.pop(conversation_id, None)
        logger.info("short_term.cleared", conversation_id=conversation_id)

    def clear_all(self) -> None:
        """Wipe every conversation buffer."""
        self._conversations.clear()
        logger.info("short_term.cleared_all")
