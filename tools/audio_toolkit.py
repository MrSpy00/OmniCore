"""Audio Toolkit — text-to-speech."""

from __future__ import annotations

from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


class AudioTextToSpeech(BaseTool):
    name = "audio_text_to_speech"
    description = "Convert text to speech and save as MP3 on the host OS."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        import edge_tts

        text = tool_input.parameters.get("text", "")
        voice = tool_input.parameters.get("voice", "en-US-AriaNeural")
        output_path = tool_input.parameters.get("output_path", "speech.mp3")
        if not text:
            return self._failure("text is required")

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            communicate = edge_tts.Communicate(text=text, voice=voice)
            await communicate.save(str(save_path))
            return self._success(
                f"Audio saved to {save_path.name}",
                data={"path": str(save_path)},
            )
        except Exception as exc:
            return self._failure(str(exc))
