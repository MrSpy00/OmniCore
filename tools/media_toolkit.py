"""Media Toolkit — YouTube audio and transcript extraction."""

from __future__ import annotations

import re
from pathlib import Path

from config.logging import get_logger
from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

logger = get_logger(__name__)


def _resolve_sandboxed(path_str: str) -> Path:
    """Resolve *path_str* within the sandbox root. Raises on escape."""
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


def _extract_video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|youtu\.be/)([\w-]{6,})", url)
    return match.group(1) if match else None


class MediaDownloadYoutubeAudio(BaseTool):
    name = "media_download_youtube_audio"
    description = "Download YouTube audio as MP3 into the sandbox."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from yt_dlp import YoutubeDL

        url = tool_input.parameters.get("url", "")
        output_path = tool_input.parameters.get("output_path", "youtube_audio.mp3")
        if not url:
            return self._failure("No URL provided")

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(save_path.with_suffix("")),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "quiet": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            final_path = save_path.with_suffix(".mp3")
            logger.info("media.youtube_audio", url=url, path=str(final_path))
            return self._success(
                f"Audio saved to {final_path.name}",
                data={"path": str(final_path)},
            )
        except Exception as exc:
            return self._failure(str(exc))


class MediaGetYoutubeTranscript(BaseTool):
    name = "media_get_youtube_transcript"
    description = "Fetch a YouTube video's transcript text."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from youtube_transcript_api import YouTubeTranscriptApi

        url = tool_input.parameters.get("url", "")
        language = tool_input.parameters.get("language", "en")
        if not url:
            return self._failure("No URL provided")

        video_id = _extract_video_id(url)
        if not video_id:
            return self._failure("Could not extract video id")

        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
            text = "\n".join(chunk.get("text", "") for chunk in transcript)
            max_chars = tool_input.parameters.get("max_chars", 12_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            logger.info("media.youtube_transcript", video_id=video_id)
            return self._success(
                f"Transcript fetched for {video_id}",
                data={"video_id": video_id, "language": language, "text": text},
            )
        except Exception as exc:
            return self._failure(str(exc))
