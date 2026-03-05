"""Network Toolkit — ping and IP discovery."""

from __future__ import annotations

import socket
import subprocess

import httpx

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class NetPing(BaseTool):
    name = "net_ping"
    description = "Ping a host and return latency output."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        host = tool_input.parameters.get("host", "")
        if not host:
            return self._failure("host is required")

        try:
            count = int(tool_input.parameters.get("count", 1))
            result = subprocess.run(
                ["ping", "-n", str(count), host],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return self._success(
                f"Ping {host} completed",
                data={"returncode": result.returncode, "output": result.stdout},
            )
        except Exception as exc:
            return self._failure(str(exc))


class NetGetIP(BaseTool):
    name = "net_get_ip"
    description = "Return internal and external IP addresses."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            hostname = socket.gethostname()
            internal_ip = socket.gethostbyname(hostname)
            async with httpx.AsyncClient(timeout=10) as client:
                external_ip = (await client.get("https://api.ipify.org")).text.strip()
            return self._success(
                "IP addresses retrieved",
                data={"internal_ip": internal_ip, "external_ip": external_ip},
            )
        except Exception as exc:
            return self._failure(str(exc))
