"""Audio Recorder Toolkit — capture microphone audio to WAV."""

from __future__ import annotations

import asyncio
from pathlib import Path

import sounddevice as sd
import soundfile as sf

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


def _resolve_sandboxed(path_str: str) -> Path:
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


class AudioRecordMicrophone(BaseTool):
    name = "audio_record_microphone"
    description = "Record microphone audio to a WAV file."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        seconds = float(tool_input.parameters.get("seconds", 5))
        sample_rate = int(tool_input.parameters.get("sample_rate", 44100))
        output_path = tool_input.parameters.get("output_path", "recording.wav")

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            data = await asyncio.to_thread(_record_audio, seconds, sample_rate)
            await asyncio.to_thread(sf.write, str(save_path), data, sample_rate)
            return self._success(
                f"Recording saved to {save_path.name}",
                data={"path": str(save_path)},
            )
        except Exception as exc:
            return self._failure(str(exc))


def _record_audio(seconds: float, sample_rate: int):
    data = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1)
    sd.wait()
    return data
