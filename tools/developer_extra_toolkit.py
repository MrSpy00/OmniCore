"""Additional developer utilities."""

from __future__ import annotations

import asyncio
import base64
import json

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class DevDecodeBase64(BaseTool):
    name = "dev_decode_base64"
    description = "Decode a Base64 string into text."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        encoded = str(self._first_param(params, "text", "data", "value", default=""))
        if not encoded:
            return self._failure("text is required")
        try:
            decoded = await asyncio.to_thread(base64.b64decode, encoded)
            return self._success(
                "Base64 decoded", data={"text": decoded.decode("utf-8", errors="replace")}
            )
        except Exception as exc:
            return self._failure(str(exc))


class DevFormatJson(BaseTool):
    name = "dev_format_json"
    description = "Format a JSON string with indentation."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        raw = str(self._first_param(params, "text", "json", "value", default=""))
        if not raw:
            return self._failure("json text is required")
        try:
            parsed = json.loads(raw)
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            return self._success("JSON formatted", data={"formatted": pretty})
        except Exception as exc:
            return self._failure(str(exc))
