"""Voice Engine — STT (speech recognition) + LLM + TTS (text-to-speech) pipeline.

Captures microphone input, transcribes via SpeechRecognition, processes through
CognitiveRouter, and speaks the response via edge-tts.
"""

from __future__ import annotations

import asyncio
import io
import tempfile
import wave
from pathlib import Path
from typing import Any

from config.logging import get_logger
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

# Lazy imports for optional dependencies
_sr = None
_speech_recognition = None
_edge_tts = None
_sounddevice = None


def _lazy_import_sr():
    global _sr, _speech_recognition
    if _sr is None:
        try:
            import speech_recognition as sr
            _sr = sr
            _speech_recognition = sr
        except ImportError:
            raise RuntimeError(
                "speech_recognition not installed. Run: uv add SpeechRecognition"
            )
    return _sr


def _lazy_import_edge_tts():
    global _edge_tts
    if _edge_tts is None:
        try:
            import edge_tts
            _edge_tts = edge_tts
        except ImportError:
            raise RuntimeError("edge-tts not installed. Run: uv add edge-tts")
    return _edge_tts


def _lazy_import_sounddevice():
    global _sounddevice
    if _sounddevice is None:
        try:
            import sounddevice as sd
            _sounddevice = sd
        except ImportError:
            raise RuntimeError("sounddevice not installed. Run: uv add sounddevice")
    return _sounddevice


class VoiceEngine:
    """Push-to-talk voice engine.

    Workflow:
      1. Record audio from microphone (or accept pre-recorded audio)
      2. Transcribe to text via Google Speech Recognition (free tier)
      3. Send text to CognitiveRouter for LLM response
      4. Convert response to speech via edge-tts
      5. Return audio bytes for playback
    """

    def __init__(
        self,
        router: CognitiveRouter,
        language: str = "tr-TR",
        tts_voice: str = "tr-TR-AhmetNeural",
    ) -> None:
        self._router = router
        self._language = language
        self._tts_voice = tts_voice
        self._conversation_id = "voice_session"

    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text using SpeechRecognition."""
        sr = _lazy_import_sr()
        recognizer = sr.Recognizer()

        # Write audio bytes to a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            with sr.AudioFile(temp_path) as source:
                audio_data = recognizer.record(source)

            # Use Google's free speech recognition
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None,
                lambda: recognizer.recognize_google(audio_data, language=self._language),
            )
            logger.info("voice.transcribed", text=text[:100])
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            logger.error("voice.stt_error", error=str(exc))
            raise RuntimeError(f"Speech recognition error: {exc}") from exc
        finally:
            Path(temp_path).unlink(missing_ok=True)

    async def record_from_microphone(
        self, duration: float = 5.0, sample_rate: int = 16000
    ) -> bytes:
        """Record audio from microphone for a fixed duration. Returns WAV bytes."""
        sd = _lazy_import_sounddevice()
        loop = asyncio.get_event_loop()

        # Record audio in a thread
        audio_data = await loop.run_in_executor(
            None,
            lambda: sd.rec(
                int(duration * sample_rate),
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
            ),
        )
        await loop.run_in_executor(None, sd.wait)

        # Convert to WAV bytes
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.tobytes())
        return buf.getvalue()

    async def synthesize_speech(self, text: str) -> bytes:
        """Convert text to speech using edge-tts. Returns MP3 bytes."""
        edge_tts = _lazy_import_edge_tts()
        communicate = edge_tts.Communicate(text, self._tts_voice)
        buf = io.BytesIO()

        loop = asyncio.get_event_loop()

        def _synthesize():
            import asyncio as _aio

            # edge-tts is async, run in a new event loop in the executor
            async def _run():
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        buf.write(chunk["data"])

            # Use the existing loop if possible, otherwise create one
            try:
                loop = _aio.get_running_loop()
                # We're already in an async context, need a different approach
                pass
            except RuntimeError:
                pass

        # edge-tts is async - collect audio chunks
        audio_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        result = b"".join(audio_chunks)
        logger.info("voice.tts_complete", text_len=len(text), audio_len=len(result))
        return result

    async def process_voice_input(self, audio_bytes: bytes) -> dict[str, Any]:
        """Full pipeline: audio -> text -> LLM -> speech.

        Returns dict with:
          - user_text: what the user said
          - response_text: LLM response
          - response_audio: TTS audio bytes (MP3)
        """
        # Step 1: Transcribe
        user_text = await self.transcribe_audio(audio_bytes)
        if not user_text.strip():
            return {
                "user_text": "",
                "response_text": "Ses anlaşılamadı. Tekrar söyler misiniz?",
                "response_audio": b"",
            }

        # Step 2: Send to LLM
        msg = Message(
            role=MessageRole.USER,
            content=user_text,
            channel="voice",
            user_id="voice_user",
        )
        response_text = await self._router.handle_message(msg, self._conversation_id)

        # Step 3: Synthesize response
        try:
            response_audio = await self.synthesize_speech(response_text)
        except Exception as exc:
            logger.error("voice.tts_failed", error=str(exc))
            response_audio = b""

        return {
            "user_text": user_text,
            "response_text": response_text,
            "response_audio": response_audio,
        }

    async def listen_and_respond(self) -> dict[str, Any]:
        """Record from mic, process, return result."""
        audio = await self.record_from_microphone(duration=5.0)
        return await self.process_voice_input(audio)

    def check_dependencies(self) -> dict[str, bool]:
        """Check which voice dependencies are available."""
        result = {}
        for name, import_fn in [
            ("speech_recognition", lambda: __import__("speech_recognition")),
            ("sounddevice", lambda: __import__("sounddevice")),
            ("edge_tts", lambda: __import__("edge_tts")),
        ]:
            try:
                import_fn()
                result[name] = True
            except (ImportError, RuntimeError):
                result[name] = False
        return result


class DuplexVoiceEngine:
    """Streaming duplex voice loop manager (backward-compatible wrapper)."""

    def __init__(self) -> None:
        self.is_streaming = False
        self.input_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.output_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._processed_chunks = 0
        self._sent_chunks = 0
        self._processing_task: asyncio.Task[None] | None = None

    @property
    def audio_queue(self) -> asyncio.Queue[bytes]:
        return self.input_audio_queue

    async def start_session(self) -> dict[str, Any]:
        if self.is_streaming:
            return {"status": "already_active", "duplex": True}
        self.is_streaming = True
        self._processed_chunks = 0
        self._sent_chunks = 0
        self._processing_task = asyncio.create_task(self._process_audio_loop())
        logger.info("voice_duplex.session_started")
        return {"status": "active", "duplex": True}

    async def stop_session(self) -> dict[str, Any]:
        self.is_streaming = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
            self._processing_task = None
        return {
            "status": "stopped",
            "duplex": False,
            "processed_chunks": self._processed_chunks,
            "sent_chunks": self._sent_chunks,
        }

    async def push_audio_chunk(self, chunk: bytes) -> None:
        if self.is_streaming and chunk:
            await self.input_audio_queue.put(chunk)

    async def get_next_output_chunk(self) -> bytes | None:
        if not self.is_streaming or self.output_audio_queue.empty():
            return None
        chunk = await self.output_audio_queue.get()
        self._sent_chunks += 1
        return chunk

    async def _process_audio_loop(self) -> None:
        while self.is_streaming:
            try:
                chunk = await asyncio.wait_for(self.input_audio_queue.get(), timeout=1.0)
                self._processed_chunks += 1
                logger.debug("voice_duplex.chunk_received", size=len(chunk))
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("voice_duplex.processing_error", error=str(exc))
