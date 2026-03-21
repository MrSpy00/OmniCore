"""Monitoring Toolkit — web change detection and local subnet scanning."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import subprocess
from pathlib import Path

import httpx

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


class WebMonitorChanges(BaseTool):
    name = "web_monitor_changes"
    description = "Fetch a URL, hash its content, and compare against previous state."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default=""))
        state_file = str(self._first_param(params, "state_file", default="web_monitor_state.txt"))
        if not url:
            return self._failure("url is required")
        if not url.startswith("http"):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.text

            digest = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            path = _resolve_sandboxed(state_file)
            old_digest = path.read_text(encoding="utf-8") if path.exists() else ""
            await asyncio.to_thread(path.write_text, digest, encoding="utf-8")
            changed = old_digest != digest and old_digest != ""
            return self._success(
                "Web monitor check completed", data={"url": url, "changed": changed, "hash": digest}
            )
        except Exception as exc:
            return self._failure(str(exc))


class SysNetworkScanner(BaseTool):
    name = "sys_network_scanner"
    description = "Ping a local subnet and report active hosts."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        subnet = str(self._first_param(params, "subnet", default="192.168.1.0/24"))
        max_hosts = int(self._first_param(params, "max_hosts", default=32) or 32)
        try:
            hosts = await asyncio.to_thread(_scan_subnet, subnet, max_hosts)
            return self._success("Network scan completed", data={"subnet": subnet, "hosts": hosts})
        except Exception as exc:
            return self._failure(str(exc))


def _scan_subnet(subnet: str, max_hosts: int) -> list[str]:
    network = ipaddress.ip_network(subnet, strict=False)
    active: list[str] = []
    for index, host in enumerate(network.hosts()):
        if index >= max_hosts:
            break
        completed = subprocess.run(
            ["ping", "-n", "1", "-w", "300", str(host)],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if completed.returncode == 0:
            active.append(str(host))
    return active
