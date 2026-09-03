"""Enterprise MCP (Model Context Protocol) Gateway.

Exposes OmniCore toolkits to external tools and IDEs (Claude Desktop, Zed, Cursor)
via standard MCP JSON-RPC 2.0 protocol.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.logging import get_logger
from models.tools import ToolInput
from tools.registry import discover_tool_classes

logger = get_logger(__name__)


class MCPServerGateway:
    """JSON-RPC 2.0 server handler for Model Context Protocol integration."""

    def __init__(self) -> None:
        self.tool_classes = {cls.name: cls for cls in discover_tool_classes(Path("tools"))}

    async def handle_request_json(self, json_str: str) -> str:
        """Parse raw JSON-RPC string and handle request."""
        try:
            req = json.loads(json_str)
            resp = await self.handle_request(req)
            return json.dumps(resp)
        except Exception as exc:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                    "id": None,
                }
            )

    async def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        """Route JSON-RPC request to appropriate handler."""
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "OmniCore-MCP-Gateway", "version": "0.1.0"},
                },
            }

        if method == "tools/list":
            tool_list = []
            for name, cls in self.tool_classes.items():
                tool_list.append(
                    {
                        "name": name,
                        "description": cls.description,
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                )
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tool_list}}

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            if tool_name not in self.tool_classes:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
                }

            tool_instance = self.tool_classes[tool_name]()
            sub_input = ToolInput(tool_name=tool_name, parameters=arguments)
            output = await tool_instance.execute(sub_input)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": output.result or output.error}],
                    "isError": output.status.value != "success",
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }
