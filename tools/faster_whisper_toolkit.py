"""Faster Whisper STT Toolkit — 100% Local Offline Speech-to-Text via CTranslate2."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path

logger = get_logger(__name__)

_MODELS: dict[str, Any] = {}


def _get_whisper_model(model_size: str = "base") -> Any:
    global _MODELS
    if model_size not in _MODELS:
        from faster_whisper import WhisperModel

        # CPU int8 delivers high-speed inference without CUDA requirement
        logger.info("faster_whisper.loading_model", model_size=model_size)
        _MODELS[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _MODELS[model_size]


def transcribe_audio_offline(
    audio_path: str | Path,
    model_size: str = "base",
    language: str = "tr",
) -> str:
    """Synchronously transcribe audio file using faster-whisper."""
    path_str = str(audio_path)
    if not os.path.exists(path_str):
        raise FileNotFoundError(f"Audio file not found: {path_str}")

    model = _get_whisper_model(model_size)
    lang = language[:2].lower() if language else "tr"
    segments, info = model.transcribe(path_str, language=lang, beam_size=5)
    return " ".join(seg.text.strip() for seg in segments)


class WhisperTranscribe(BaseTool):
    """Local, offline speech transcription tool using faster-whisper."""

    name = "whisper_transcribe"
    description = (
        "Transcribe local audio file (WAV, MP3, M4A) to text using faster-whisper "
        "CTranslate2 offline engine. Parameter: audio_path, optional: model_size (tiny/base/small/medium), language."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = tool_input.parameters or {}
        raw_path = str(params.get("audio_path") or params.get("path") or "").strip()
        if not raw_path:
            return self._failure("audio_path parameter is required")

        model_size = str(params.get("model_size") or "base").strip().lower()
        language = str(params.get("language") or "tr").strip()

        try:
            target_path, _ = resolve_user_path(raw_path)
            if not target_path.exists():
                return self._failure(f"Audio file does not exist: {target_path}")

            loop = asyncio.get_event_loop()
            transcription = await loop.run_in_executor(
                None,
                lambda: transcribe_audio_offline(target_path, model_size=model_size, language=language),
            )
            return self._success(
                f"Transcribed successfully ({len(transcription)} characters)",
                data={
                    "text": transcription,
                    "model_size": model_size,
                    "language": language,
                    "path": str(target_path),
                },
            )
        except Exception as exc:
            logger.error("whisper_transcribe.error", error=str(exc))
            return self._failure(f"Transcription failed: {exc}")
