"""Media Toolkit — YouTube audio and transcript extraction."""

from __future__ import annotations

import re
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


def _extract_video_id(url: str) -> str | None:
    match = re.search(r"(?:v=|youtu\.be/)([\w-]{6,})", url)
    return match.group(1) if match else None


class MediaDownloadYoutubeAudio(BaseTool):
    name = "media_download_youtube_audio"
    description = "Download YouTube audio as MP3/M4A to the host OS."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from typing import Any, cast

        from yt_dlp import YoutubeDL

        url = tool_input.parameters.get("url", "")
        output_path = tool_input.parameters.get("output_path", "youtube_audio.mp3")
        if not url:
            return self._failure("No URL provided")

        try:
            save_path = _resolve_sandboxed(output_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            ydl_opts: dict[str, Any] = {
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
            with YoutubeDL(cast(Any, ydl_opts)) as ydl:  # type: ignore[arg-type,call-arg]
                ydl.download([url])

            final_path = save_path.with_suffix(".mp3")
            return self._success(
                f"Audio saved to {final_path.name}",
                data={"path": str(final_path)},
            )
        except Exception as exc:
            return self._failure(str(exc))


class MediaGetYoutubeTranscript(BaseTool):
    name = "media_get_youtube_transcript"
    description = "Fetch the transcript for a YouTube video by URL or ID."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from typing import Any, cast

        from youtube_transcript_api import YouTubeTranscriptApi

        url = tool_input.parameters.get("url")
        video_id = tool_input.parameters.get("video_id")
        language = tool_input.parameters.get("language", "en")
        if not url and not video_id:
            return self._failure("url or video_id is required")

        if not video_id and url:
            video_id = _extract_video_id(url)

        if not video_id:
            return self._failure("Could not extract video id")

        try:
            transcript: Any = cast(Any, YouTubeTranscriptApi).get_transcript(  # type: ignore[attr-defined,call-arg]
                video_id, languages=[language]
            )
            text = "\n".join(chunk.get("text", "") for chunk in transcript)
            max_chars = tool_input.parameters.get("max_chars", 12_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"
            return self._success(
                f"Transcript fetched for {video_id}",
                data={"video_id": video_id, "language": language, "text": text},
            )
        except Exception as exc:
            return self._failure(str(exc))
