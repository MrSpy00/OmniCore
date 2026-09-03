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
            raise RuntimeError("speech_recognition not installed. Run: uv add SpeechRecognition")
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
        self._vad: Any = None
        try:
            from interfaces.vad_engine import VADEngine

            self._vad = VADEngine()
            self._vad.initialize()
        except Exception:
            self._vad = None

    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes — Google STT öncelikli, faster-whisper fallback."""
        import os

        force_offline = os.environ.get("OMNICORE_OFFLINE_STT", "").strip() in ("1", "true", "True")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            if not force_offline:
                try:
                    sr = _lazy_import_sr()
                    recognizer = sr.Recognizer()
                    with sr.AudioFile(temp_path) as source:
                        audio_data = recognizer.record(source)

                    loop = asyncio.get_event_loop()
                    text = await loop.run_in_executor(
                        None,
                        lambda: recognizer.recognize_google(audio_data, language=self._language),
                    )
                    if text and text.strip():
                        logger.info("voice.transcribed_google", text=text[:100])
                        return text
                except Exception:
                    pass

            text = await self._transcribe_whisper_offline(temp_path)
            if text:
                logger.info("voice.transcribed_whisper", text=text[:100])
                return text
            return ""
        finally:
            Path(temp_path).unlink(missing_ok=True)

    async def _transcribe_whisper_offline(self, wav_path: str) -> str:
        """faster-whisper CTranslate2 ile çevrimdışı STT."""
        try:
            from tools.faster_whisper_toolkit import transcribe_audio_offline

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: transcribe_audio_offline(wav_path, model_size="base", language=self._language[:2]),
            )
        except Exception as exc:
            logger.debug("voice.whisper_fallback_failed", error=str(exc))
            return ""

    async def speak_and_monitor(
        self,
        text: str,
        on_interrupted: Any = None,
    ) -> bool:
        """Play EdgeTTS synthesized speech while concurrently monitoring microphone for user barge-in.

        If user speaks (VAD positive or high energy), immediately stops the output stream (15-20ms)
        and calls on_interrupted callback. Returns True if interrupted, False if finished normally.
        """
        import numpy as np
        import sounddevice as sd
        import soundfile as sf

        audio_mp3 = await self.synthesize_speech(text)
        if not audio_mp3:
            return False

        try:
            samples, sample_rate = sf.read(io.BytesIO(audio_mp3), dtype="float32")
        except Exception as exc:
            logger.error("voice.decode_error", error=str(exc))
            return False

        if samples.ndim == 1:
            samples = samples.reshape(-1, 1)

        interrupted = False
        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()

        def mic_callback(indata, frames, time_info, status):
            nonlocal interrupted
            if interrupted or stop_event.is_set():
                return
            raw_bytes = (indata * 32767.0).astype(np.int16).tobytes()
            detected = False
            if self._vad and getattr(self._vad, "_initialized", False):
                detected = self._vad.is_speech(raw_bytes)
            else:
                detected = _calculate_rms(raw_bytes) > 650.0

            if detected:
                interrupted = True
                loop.call_soon_threadsafe(stop_event.set)
                if self._vad:
                    self._vad.reset()
                if on_interrupted and callable(on_interrupted):
                    try:
                        on_interrupted()
                    except Exception:
                        pass

        mic_stream = None
        try:
            mic_stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=512,
                callback=mic_callback,
            )
            mic_stream.start()
        except Exception as exc:
            logger.warning("voice.mic_monitor_stream_failed", error=str(exc))

        block_size = 1024
        total_frames = len(samples)
        out_stream = None
        try:
            out_stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=samples.shape[1],
                dtype="float32",
                blocksize=block_size,
            )
            out_stream.start()

            for i in range(0, total_frames, block_size):
                if interrupted or stop_event.is_set():
                    break
                chunk = samples[i : i + block_size]
                out_stream.write(chunk)
                await asyncio.sleep(0.001)

        finally:
            if out_stream:
                try:
                    out_stream.stop()
                    out_stream.close()
                except Exception:
                    pass
            if mic_stream:
                try:
                    mic_stream.stop()
                    mic_stream.close()
                except Exception:
                    pass

        if interrupted:
            logger.info("voice.barge_in_interrupted", text=text[:50])
            return True
        return False

    async def record_from_microphone(self, duration: float = 5.0, sample_rate: int = 16000) -> bytes:
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


def _calculate_rms(chunk: bytes) -> float:
    """Calculate Root Mean Square (RMS) energy level of a 16-bit PCM audio chunk."""
    if not chunk or len(chunk) < 2:
        return 0.0
    import audioop

    try:
        return float(audioop.rms(chunk, 2))
    except Exception:
        # Fallback if audioop is unavailable (e.g. Python 3.13+)
        import struct

        count = len(chunk) // 2
        format_str = f"<{count}h"
        try:
            shorts = struct.unpack(format_str, chunk[: count * 2])
            sum_squares = sum(s * s for s in shorts)
            return (sum_squares / count) ** 0.5
        except Exception:
            return 0.0


class DuplexVoiceEngine:
    """Streaming duplex voice loop manager with real-time Barge-In (Interruption) support."""

    def __init__(self, energy_threshold: float = 650.0) -> None:
        self.is_streaming = False
        self.is_speaking = False
        self.input_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.output_audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._processed_chunks = 0
        self._sent_chunks = 0
        self._interrupted_count = 0
        self._processing_task: asyncio.Task[None] | None = None
        self._energy_threshold = energy_threshold
        self._barge_in_event = asyncio.Event()
        self._vad: Any = None
        try:
            from interfaces.vad_engine import VADEngine

            self._vad = VADEngine()
            self._vad.initialize()
        except Exception:
            self._vad = None

    @property
    def audio_queue(self) -> asyncio.Queue[bytes]:
        return self.input_audio_queue

    async def start_session(self) -> dict[str, Any]:
        if self.is_streaming:
            return {"status": "already_active", "duplex": True, "barge_in": True}
        self.is_streaming = True
        self.is_speaking = False
        self._processed_chunks = 0
        self._sent_chunks = 0
        self._interrupted_count = 0
        self._barge_in_event.clear()
        self._processing_task = asyncio.create_task(self._process_audio_loop())
        logger.info("voice_duplex.session_started", barge_in_enabled=True)
        return {"status": "active", "duplex": True, "barge_in": True}

    async def stop_session(self) -> dict[str, Any]:
        self.is_streaming = False
        self.is_speaking = False
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
            "interrupted_count": self._interrupted_count,
        }

    def interrupt_playback(self) -> bool:
        """Immediately discard queued output audio if user speaks (Barge-In)."""
        if not self.is_speaking and self.output_audio_queue.empty():
            return False

        # Drain output queue
        drained = 0
        while not self.output_audio_queue.empty():
            try:
                self.output_audio_queue.get_nowait()
                drained += 1
            except Exception:
                break

        self.is_speaking = False
        self._interrupted_count += 1
        self._barge_in_event.set()
        logger.info("voice_duplex.barge_in_triggered", drained_chunks=drained)
        return True

    async def push_audio_chunk(self, chunk: bytes) -> None:
        if self.is_streaming and chunk:
            # VAD tabanlı barge-in kontrolü (Silero VAD öncelikli, RMS fallback)
            speech_detected = False
            if self._vad and self._vad._initialized:
                speech_detected = self._vad.is_speech(chunk)
            else:
                rms = _calculate_rms(chunk)
                speech_detected = rms > self._energy_threshold

            if self.is_speaking and speech_detected:
                self.interrupt_playback()

            await self.input_audio_queue.put(chunk)

    async def queue_speech_output(self, chunk: bytes) -> None:
        """Queue a synthesized speech chunk to be delivered to the speaker."""
        if self.is_streaming and chunk:
            self.is_speaking = True
            await self.output_audio_queue.put(chunk)

    async def get_next_output_chunk(self) -> bytes | None:
        if not self.is_streaming or self.output_audio_queue.empty():
            self.is_speaking = False
            return None
        chunk = await self.output_audio_queue.get()
        self._sent_chunks += 1
        return chunk

    async def _process_audio_loop(self) -> None:
        while self.is_streaming:
            try:
                chunk = await asyncio.wait_for(self.input_audio_queue.get(), timeout=1.0)
                self._processed_chunks += 1
                rms = _calculate_rms(chunk)
                logger.debug("voice_duplex.chunk_received", size=len(chunk), rms=rms)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("voice_duplex.processing_error", error=str(exc))
