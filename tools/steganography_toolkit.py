"""Steganography Toolkit — hide and reveal messages in images."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from PIL import Image

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.base import resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


class StegHideMessage(BaseTool):
    name = "steg_hide_message"
    description = "Hide a short message in a PNG image."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        image_path = tool_input.parameters.get("image_path", "")
        message = tool_input.parameters.get("message", "")
        output_path = tool_input.parameters.get("output_path", "steg.png")
        if not image_path or not message:
            return self._failure("image_path and message are required")

        try:
            src = _resolve_sandboxed(image_path)
            dest = _resolve_sandboxed(output_path)
            await asyncio.to_thread(_encode_message, src, dest, message)
            return self._success("Message hidden", data={"path": str(dest)})
        except Exception as exc:
            return self._failure(str(exc))


class StegRevealMessage(BaseTool):
    name = "steg_reveal_message"
    description = "Reveal a hidden message from a PNG image."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        image_path = tool_input.parameters.get("image_path", "")
        if not image_path:
            return self._failure("image_path is required")

        try:
            src = _resolve_sandboxed(image_path)
            message = await asyncio.to_thread(_decode_message, src)
            return self._success("Message revealed", data={"message": message})
        except Exception as exc:
            return self._failure(str(exc))


def _encode_message(src: Path, dest: Path, message: str) -> None:
    img = Image.open(src).convert("RGB")
    pixels = img.load()
    if pixels is None:
        raise ValueError("Unable to access image pixels")
    pixel_access = cast(Any, pixels)
    message_bytes = message.encode("utf-8") + b"\x00"
    bits = "".join(f"{b:08b}" for b in message_bytes)
    width, height = img.size
    idx = 0
    for y in range(height):
        for x in range(width):
            if idx >= len(bits):
                img.save(dest)
                return
            r, g, b = cast(tuple[int, int, int], pixel_access[x, y])
            r = (r & ~1) | int(bits[idx])
            idx += 1
            pixel_access[x, y] = (r, g, b)
    img.save(dest)


def _decode_message(src: Path) -> str:
    img = Image.open(src).convert("RGB")
    pixels = img.load()
    if pixels is None:
        raise ValueError("Unable to access image pixels")
    pixel_access = cast(Any, pixels)
    width, height = img.size
    bits = []
    for y in range(height):
        for x in range(width):
            r, g, b = cast(tuple[int, int, int], pixel_access[x, y])
            bits.append(str(r & 1))
    bytes_out = []
    for i in range(0, len(bits), 8):
        byte = int("".join(bits[i : i + 8]), 2)
        if byte == 0:
            break
        bytes_out.append(byte)
    return bytes(bytes_out).decode("utf-8", errors="replace")
