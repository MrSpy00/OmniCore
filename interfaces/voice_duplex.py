"""Real-Time Duplex Voice Engine — Streaming audio loop for low-latency voice interactions."""

from __future__ import annotations

import asyncio
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


class DuplexVoiceEngine:
    """Streaming duplex voice loop manager supporting bi-directional audio queues."""

    def __init__(self) -> None:
        self.is_streaming = False
        self.input_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.output_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._processed_chunks = 0
        self._sent_chunks = 0
        self._processing_task: asyncio.Task[None] | None = None

    @property
    def audio_queue(self) -> asyncio.Queue[bytes]:
        """Backward-compatible alias for input audio queue."""
        return self.input_audio_queue

    async def start_session(self) -> dict[str, Any]:
        """Initialize and start duplex voice session."""
        if self.is_streaming:
            return {"status": "already_active", "duplex": True}

        self.is_streaming = True
        self._processed_chunks = 0
        self._sent_chunks = 0
        self._processing_task = asyncio.create_task(self._process_audio_loop())
        logger.info("voice_duplex.session_started")
        return {"status": "active", "duplex": True}

    async def stop_session(self) -> dict[str, Any]:
        """Stop active duplex voice session."""
        self.is_streaming = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self._processing_task = None

        logger.info(
            "voice_duplex.session_stopped",
            processed=self._processed_chunks,
            sent=self._sent_chunks,
        )
        return {
            "status": "stopped",
            "duplex": False,
            "processed_chunks": self._processed_chunks,
            "sent_chunks": self._sent_chunks,
        }

    async def push_audio_chunk(self, chunk: bytes) -> None:
        """Push PCM audio chunk into real-time processing queue."""
        if self.is_streaming and chunk:
            await self.input_audio_queue.put(chunk)

    async def get_next_output_chunk(self) -> bytes | None:
        """Pop next synthesized audio chunk from output queue."""
        if not self.is_streaming or self.output_audio_queue.empty():
            return None
        chunk = await self.output_audio_queue.get()
        self._sent_chunks += 1
        return chunk

    async def _process_audio_loop(self) -> None:
        """Background loop processing incoming audio chunks."""
        while self.is_streaming:
            try:
                chunk = await asyncio.wait_for(self.input_audio_queue.get(), timeout=1.0)
                self._processed_chunks += 1
                # Forward to response processing pipeline if needed
                logger.debug("voice_duplex.chunk_received", size=len(chunk))
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("voice_duplex.processing_error", error=str(exc))
