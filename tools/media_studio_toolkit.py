"""Media studio and creation toolkit."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


class MediaConvertVideo(BaseTool):
    name = "media_convert_video"
    description = "Convert a video file to MP4 using ffmpeg."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        source = str(self._first_param(params, "source", "path", default=""))
        output_path = str(self._first_param(params, "output_path", default="converted.mp4"))
        if not source:
            return self._failure("source is required")
        try:
            src = _resolve_sandboxed(source)
            dst = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_ffmpeg_convert_video, src, dst)
            return self._success("Video converted", data={"path": str(dst)})
        except Exception as exc:
            return self._failure(str(exc))


class MediaExtractAudio(BaseTool):
    name = "media_extract_audio"
    description = "Extract audio from a video file as MP3."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        source = str(self._first_param(params, "source", "path", default=""))
        output_path = str(self._first_param(params, "output_path", default="audio.mp3"))
        if not source:
            return self._failure("source is required")
        try:
            src = _resolve_sandboxed(source)
            dst = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_ffmpeg_extract_audio, src, dst)
            return self._success("Audio extracted", data={"path": str(dst)})
        except Exception as exc:
            return self._failure(str(exc))


class MediaWatermarkImage(BaseTool):
    name = "media_watermark_image"
    description = "Overlay watermark text onto an image."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        source = str(self._first_param(params, "source", "path", default=""))
        text = str(self._first_param(params, "text", "watermark", default=""))
        output_path = str(self._first_param(params, "output_path", default="watermarked.png"))
        if not source or not text:
            return self._failure("source and text are required")
        try:
            src = _resolve_sandboxed(source)
            dst = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_watermark_image, src, dst, text)
            return self._success("Image watermarked", data={"path": str(dst)})
        except Exception as exc:
            return self._failure(str(exc))


class MediaGenerateTtsHuman(BaseTool):
    name = "media_generate_tts_human"
    description = "Generate natural TTS audio via Edge-TTS."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from tools.audio_toolkit import AudioTextToSpeech

        return await AudioTextToSpeech().execute(tool_input)


class MediaExtractTextFromVideo(BaseTool):
    name = "media_extract_text_from_video"
    description = "Extract text transcript from a local video by converting audio and applying STT."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        import tempfile

        import speech_recognition as sr  # type: ignore[import-not-found]

        params = self._params(tool_input)
        source = str(self._first_param(params, "source", "path", "video_path", default="")).strip()
        language = str(self._first_param(params, "language", default="en-US")).strip() or "en-US"
        if not source:
            return self._failure("source is required")

        src = _resolve_sandboxed(source)
        if not src.exists():
            return self._failure(f"source not found: {src}")

        wav_path = Path(tempfile.gettempdir()) / f"omnicore_stt_{src.stem}.wav"
        try:
            await asyncio.to_thread(_ffmpeg_extract_wav_mono, src, wav_path)
            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_path)) as audio_file:
                audio_data = recognizer.record(audio_file)
            text = await asyncio.to_thread(recognizer.recognize_google, audio_data, language)
            return self._success(
                "Video text extraction completed",
                data={
                    "source": str(src),
                    "language": language,
                    "text": text,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass


def _ffmpeg_convert_video(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), str(dst)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def _ffmpeg_extract_audio(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-vn", "-acodec", "mp3", str(dst)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def _watermark_image(src: Path, dst: Path, text: str) -> None:
    image = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    draw.text((20, image.height - 40), text, fill=(255, 255, 255, 180), font=font)
    combined = Image.alpha_composite(image, overlay)
    combined.convert("RGB").save(dst)


def _ffmpeg_extract_wav_mono(src: Path, dst: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(dst),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
