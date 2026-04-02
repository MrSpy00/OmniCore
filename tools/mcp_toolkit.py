"""MCP bridge tools for local integration stubs."""

from __future__ import annotations

import asyncio
import json

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


class SysMcpBridge(BaseTool):
    name = "sys_mcp_bridge"
    description = "Read/write local MCP bridge envelopes from JSON files."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", default="ping")).strip().lower()
        path_raw = str(self._first_param(params, "path", default="./data/mcp_bridge.json")).strip()
        path, _ = resolve_user_path(path_raw)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return self._failure(f"Cannot prepare path: {exc}")

        if action == "ping":
            return self._success(
                "MCP bridge reachable",
                data={"action": action, "path": str(path), "status": "ok"},
            )

        if action == "write":
            payload = params.get("payload", {})

            def _write() -> None:
                path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

            try:
                await asyncio.to_thread(_write)
                return self._success("MCP envelope written", data={"path": str(path)})
            except Exception as exc:
                return self._failure(str(exc))

        if action == "read":
            if not path.exists():
                return self._failure(f"Bridge file not found: {path}")

            def _read() -> dict:
                return json.loads(path.read_text(encoding="utf-8"))

            try:
                data = await asyncio.to_thread(_read)
                return self._success("MCP envelope read", data={"path": str(path), "payload": data})
            except Exception as exc:
                return self._failure(str(exc))

        return self._failure("Unsupported action. Use ping|read|write")
