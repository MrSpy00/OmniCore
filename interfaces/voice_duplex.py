"""Real-Time Duplex Voice Engine — Streaming audio loop for low-latency voice interactions."""

from __future__ import annotations

import asyncio
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


class DuplexVoiceEngine:
    """Streaming duplex voice loop manager."""

    def __init__(self) -> None:
        self.is_streaming = False
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def start_session(self) -> dict[str, Any]:
        """Initialize and start duplex voice session."""
        self.is_streaming = True
        logger.info("voice_duplex.session_started")
        return {"status": "active", "duplex": True}

    async def stop_session(self) -> dict[str, Any]:
        """Stop active duplex voice session."""
        self.is_streaming = False
        logger.info("voice_duplex.session_stopped")
        return {"status": "stopped", "duplex": False}

    async def push_audio_chunk(self, chunk: bytes) -> None:
        """Push PCM audio chunk into real-time processing queue."""
        if self.is_streaming:
            await self.audio_queue.put(chunk)
