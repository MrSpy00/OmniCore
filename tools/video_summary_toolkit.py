"""Video Summary Toolkit — YouTube transcript extraction and summarization."""

from __future__ import annotations

import asyncio

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class VideoSummarize(BaseTool):
    """Extract YouTube video transcript and generate a summary."""

    name = "video_summarize"
    description = (
        "Extract transcript/captions from a YouTube video and return a clean text summary. "
        "Parameters: url (YouTube URL), language (optional, default: auto-detect)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "link", "video_url", default="") or "").strip()
        if not url:
            return self._failure("url parameter is required (YouTube URL).")

        video_id = _extract_video_id(url)
        if not video_id:
            return self._failure(f"Could not extract video ID from URL: {url}")

        try:
            transcript_text = await asyncio.to_thread(_fetch_transcript, video_id)
            if not transcript_text:
                return self._failure("No transcript available for this video.")

            summary = _clean_transcript(transcript_text)
            return self._success(
                f"Transcript extracted ({len(summary)} chars)",
                data={
                    "video_id": video_id,
                    "url": url,
                    "transcript": summary[:8000],
                    "char_count": len(summary),
                },
            )
        except Exception as exc:
            return self._failure(f"Failed to extract transcript: {exc}")


class VideoGetInfo(BaseTool):
    """Get basic metadata about a YouTube video."""

    name = "video_get_info"
    description = "Get YouTube video title and basic info using yt-dlp. Parameters: url (YouTube URL)."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "link", "video_url", default="") or "").strip()
        if not url:
            return self._failure("url parameter is required.")

        try:
            info = await asyncio.to_thread(_get_video_info, url)
            return self._success("Video info retrieved", data=info)
        except Exception as exc:
            return self._failure(f"Failed to get video info: {exc}")


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    import re

    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _fetch_transcript(video_id: str) -> str:
    """Fetch transcript using youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi

    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    return " ".join(entry.text for entry in transcript.snippets if entry.text.strip())


def _clean_transcript(text: str) -> str:
    """Clean transcript text by removing filler words and normalizing."""
    import re

    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_video_info(url: str) -> dict:
    """Get video metadata using yt-dlp."""
    import yt_dlp

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", ""),
            "view_count": info.get("view_count", 0),
            "description": (info.get("description", "") or "")[:500],
        }
