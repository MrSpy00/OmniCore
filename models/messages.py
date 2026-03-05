"""Pydantic models for internal message passing between modules."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Who produced the message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """A single message in a conversation."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    role: MessageRole
    content: str
    channel: str = "unknown"  # telegram, cli, rest, scheduler
    user_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)


class Conversation(BaseModel):
    """An ordered collection of messages forming a conversation."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def add(self, message: Message) -> None:
        """Append a message to the conversation."""
        self.messages.append(message)

    @property
    def last_user_message(self) -> Message | None:
        """Return the most recent user message, or None."""
        for msg in reversed(self.messages):
            if msg.role == MessageRole.USER:
                return msg
        return None

    def to_langchain_messages(self) -> list[tuple[str, str]]:
        """Convert to LangChain-compatible (role, content) tuples."""
        return [(msg.role.value, msg.content) for msg in self.messages]
