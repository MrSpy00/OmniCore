"""Network and infrastructure toolkit."""

from __future__ import annotations

import asyncio
import ftplib
import socket
import subprocess

import paramiko

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class NetStealthPortScan(BaseTool):
    name = "net_stealth_port_scan"
    description = "Scan common ports on a host and report which are open."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        host = str(self._first_param(params, "host", "target", default=""))
        ports = params.get("ports", [21, 22, 80, 443, 3389])
        if not host:
            return self._failure("host is required")
        try:
            open_ports = await asyncio.to_thread(_scan_ports, host, ports)
            return self._success(
                "Port scan completed", data={"host": host, "open_ports": open_ports}
            )
        except Exception as exc:
            return self._failure(str(exc))


class NetTraceroute(BaseTool):
    name = "net_traceroute"
    description = "Run Windows tracert against a host."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        host = str(self._first_param(params, "host", "target", default=""))
        if not host:
            return self._failure("host is required")
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                ["tracert", host],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return self._success(
                "Traceroute completed", data={"output": completed.stdout or completed.stderr}
            )
        except Exception as exc:
            return self._failure(str(exc))


class NetStartLocalServer(BaseTool):
    name = "net_start_local_server"
    description = "Start a temporary local HTTP server on a given port."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        port = int(self._first_param(params, "port", default=8000) or 8000)
        directory = str(self._first_param(params, "directory", "path", default="."))
        try:
            process = await asyncio.to_thread(
                subprocess.Popen,
                ["python", "-m", "http.server", str(port)],
                cwd=directory,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return self._success(
                "Local server started",
                data={"pid": process.pid, "port": port, "directory": directory},
            )
        except Exception as exc:
            return self._failure(str(exc))


class NetFtpClient(BaseTool):
    name = "net_ftp_client"
    description = "Connect to FTP and list or download files."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        host = str(self._first_param(params, "host", default=""))
        username = str(self._first_param(params, "username", "user", default="anonymous"))
        password = str(self._first_param(params, "password", default="anonymous@"))
        action = str(self._first_param(params, "action", default="list")).lower()
        remote_path = str(self._first_param(params, "remote_path", default="."))
        if not host:
            return self._failure("host is required")
        try:
            data = await asyncio.to_thread(
                _ftp_action, host, username, password, action, remote_path
            )
            return self._success("FTP action completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class NetSshExecute(BaseTool):
    name = "net_ssh_execute"
    description = "Connect to SSH and execute a command."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        host = str(self._first_param(params, "host", default=""))
        username = str(self._first_param(params, "username", "user", default=""))
        password = str(self._first_param(params, "password", default=""))
        command = str(self._first_param(params, "command", "cmd", default=""))
        port = int(self._first_param(params, "port", default=22) or 22)
        if not host or not username or not command:
            return self._failure("host, username, and command are required")
        try:
            result = await asyncio.to_thread(_ssh_execute, host, port, username, password, command)
            return self._success("SSH command completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class NetWifiConnect(BaseTool):
    name = "net_wifi_connect"
    description = "Connect to a Wi-Fi network by SSID using netsh on Windows."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        ssid = str(self._first_param(params, "ssid", "name", "network", default=""))
        password = str(self._first_param(params, "password", "key", "pass", default=""))
        if not ssid:
            return self._failure("ssid is required")
        try:
            result = await asyncio.to_thread(_wifi_connect, ssid, password)
            return self._success(
                f"Wi-Fi connection attempt for '{ssid}'",
                data={"ssid": ssid, "output": result},
            )
        except Exception as exc:
            return self._failure(str(exc))


def _scan_ports(host: str, ports: list[int]) -> list[int]:
    open_ports: list[int] = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, int(port))) == 0:
                open_ports.append(int(port))
    return open_ports


def _ftp_action(
    host: str, username: str, password: str, action: str, remote_path: str
) -> dict[str, object]:
    with ftplib.FTP(host, timeout=15) as ftp:
        ftp.login(username, password)
        if action == "list":
            files = ftp.nlst(remote_path)
            return {"files": files}
        raise ValueError("Unsupported FTP action")


def _ssh_execute(
    host: str, port: int, username: str, password: str, command: str
) -> dict[str, str | int]:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=port, username=username, password=password, timeout=10)
        stdin, stdout, stderr = client.exec_command(command, timeout=30)
        return {
            "stdout": stdout.read().decode("utf-8", errors="replace"),
            "stderr": stderr.read().decode("utf-8", errors="replace"),
            "port": port,
        }
    finally:
        client.close()


def _wifi_connect(ssid: str, password: str) -> str:
    """Connect to a Wi-Fi network using netsh.

    If a profile for the SSID already exists, connects directly.
    Otherwise, creates a temporary XML profile, adds it, then connects.
    """
    import os
    import tempfile

    # First try direct connect (profile may already exist).
    completed = subprocess.run(
        ["netsh", "wlan", "connect", f"name={ssid}"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode == 0 and "successfully" in completed.stdout.lower():
        return completed.stdout.strip()

    # Create a temporary profile XML and add it.
    if not password:
        raise RuntimeError(f"No existing profile for '{ssid}' and no password provided.")

    auth = "WPA2PSK"
    encryption = "AES"
    profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM><security>
        <authEncryption><authentication>{auth}</authentication>
        <encryption>{encryption}</encryption><useOneX>false</useOneX></authEncryption>
        <sharedKey><keyType>passPhrase</keyType><protected>false</protected>
        <keyMaterial>{password}</keyMaterial></sharedKey>
    </security></MSM>
</WLANProfile>"""

    tmp_path = os.path.join(tempfile.gettempdir(), f"omnicore_wifi_{ssid}.xml")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(profile_xml)

        add_result = subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={tmp_path}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if add_result.returncode != 0:
            raise RuntimeError(f"Failed to add profile: {add_result.stderr}")

        connect_result = subprocess.run(
            ["netsh", "wlan", "connect", f"name={ssid}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return (connect_result.stdout + connect_result.stderr).strip()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
