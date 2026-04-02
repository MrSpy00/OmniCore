"""Network and infrastructure toolkit."""

from __future__ import annotations

import asyncio
import ftplib
import ipaddress
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path

import paramiko

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()


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


class NetMonitorLiveTraffic(BaseTool):
    name = "net_monitor_live_traffic"
    description = "Run netstat -ano and show active remote IP communications."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            raw_output = (completed.stdout or "") + (completed.stderr or "")
            parsed = _parse_netstat_live_connections(raw_output)
            return self._success(
                "Live traffic snapshot collected",
                data={
                    "connections": parsed,
                    "connection_count": len(parsed),
                    "raw_output": raw_output,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class OsDeepSearch(BaseTool):
    name = "os_deep_search"
    description = "Search any drive/root for files by name with optimized native search backends."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        filename = str(self._first_param(params, "filename", "name", "query", default="")).strip()
        if not filename:
            return self._failure("filename is required")

        search_root_raw = str(
            self._first_param(params, "search_root", "root", "path", default="")
        ).strip()
        if search_root_raw:
            search_root, _ = resolve_user_path(search_root_raw)
        else:
            search_root = _default_search_root()

        limit = int(self._first_param(params, "limit", default=500) or 500)
        timeout_seconds = int(
            self._first_param(params, "timeout_seconds", "timeout", default=180) or 180
        )
        timeout_seconds = max(10, timeout_seconds)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_deep_search_native, filename, search_root, limit),
                timeout=timeout_seconds,
            )
            return self._success(
                f"Deep search completed ({result.get('count', 0)} matches)",
                data=result,
            )
        except TimeoutError:
            return self._failure(
                "Search timed out after "
                f"{timeout_seconds}s for root '{search_root}' and pattern '{filename}'"
            )
        except Exception as exc:
            return self._failure(str(exc))


class NetInterceptAndAnalyze(BaseTool):
    name = "net_intercept_and_analyze"
    description = "Capture a live socket snapshot and return a basic risk analysis."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        max_rows = int(self._first_param(params, "max_rows", "limit", default=200) or 200)
        max_rows = max(10, min(max_rows, 2000))

        try:
            snapshot = await asyncio.to_thread(_collect_socket_snapshot)
            analyzed = _analyze_socket_snapshot(snapshot)
            total = len(analyzed)
            return self._success(
                f"Intercepted {total} socket rows and analyzed network risk",
                data={
                    "count": total,
                    "rows": analyzed[:max_rows],
                    "suspicious_count": sum(1 for row in analyzed if row.get("risk") != "low"),
                },
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


def _parse_netstat_live_connections(raw_output: str) -> list[dict[str, str]]:
    connections: list[dict[str, str]] = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("proto"):
            continue

        parts = re.split(r"\s+", line)
        if len(parts) < 4:
            continue

        proto = parts[0]
        if proto.upper() == "TCP" and len(parts) >= 5:
            local = parts[1]
            remote = parts[2]
            state = parts[3]
            pid = parts[4]
        elif proto.upper() == "UDP" and len(parts) >= 4:
            local = parts[1]
            remote = parts[2]
            state = ""
            pid = parts[3]
        else:
            continue

        remote_ip = remote
        if ":" in remote:
            remote_ip = remote.rsplit(":", 1)[0]
        remote_ip = remote_ip.strip("[]")
        if remote_ip in {"0.0.0.0", "*", "::"}:
            continue

        connections.append(
            {
                "protocol": proto,
                "local": local,
                "remote": remote,
                "remote_ip": remote_ip,
                "state": state,
                "pid": pid,
            }
        )
    return connections


def _default_search_root() -> Path:
    return _RUNTIME.default_search_root()


def _deep_search_native(filename: str, search_root: Path, limit: int) -> dict[str, object]:
    safe_limit = max(1, min(int(limit), 10_000))
    if _RUNTIME.is_windows:
        return _deep_search_windows(filename, search_root, safe_limit)
    return _deep_search_posix(filename, search_root, safe_limit)


def _deep_search_windows(filename: str, search_root: Path, limit: int) -> dict[str, object]:
    root = search_root

    # Handle bare drive letters (e.g., "D:") by normalizing to root.
    root_str = str(root)
    if re.fullmatch(r"(?i)[a-z]:", root_str):
        root = Path(f"{root_str}\\")

    # Prefer Everything CLI if available, then filter to requested root.
    everything = shutil.which("es")
    if everything:
        completed = subprocess.run(
            [everything, filename],
            capture_output=True,
            text=True,
            timeout=90,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        root_norm = str(root).lower()
        matches = [ln for ln in lines if ln.lower().startswith(root_norm)]
        matches = matches[:limit]
        return {
            "engine": "everything_cli",
            "search_root": str(root),
            "count": len(matches),
            "matches": matches,
            "raw_output": output,
            "returncode": completed.returncode,
        }

    escaped_root = str(root).replace("'", "''")
    escaped_name = filename.replace("'", "''")
    # Prefer .NET enumeration to explicitly skip inaccessible/protected directories.
    ps = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$root='{escaped_root}'; $name='{escaped_name}'; "
        "$opts=[System.IO.EnumerationOptions]::new(); "
        "$opts.RecurseSubdirectories=$true; "
        "$opts.IgnoreInaccessible=$true; "
        "$opts.ReturnSpecialDirectories=$false; "
        + (
            "$opts.AttributesToSkip=[System.IO.FileAttributes]::System "
            "-bor [System.IO.FileAttributes]::Offline; "
        )
        + "[System.IO.Directory]::EnumerateFiles($root,$name,$opts)"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=240,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    matches = lines[:limit]
    return {
        "engine": "powershell_get_childitem",
        "search_root": str(root),
        "count": len(matches),
        "matches": matches,
        "raw_output": output,
        "returncode": completed.returncode,
    }


def _deep_search_posix(filename: str, search_root: Path, limit: int) -> dict[str, object]:
    completed = subprocess.run(
        ["find", str(search_root), "-type", "f", "-name", filename],
        capture_output=True,
        text=True,
        timeout=240,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    lines = [ln.strip() for ln in (completed.stdout or "").splitlines() if ln.strip()]
    matches = lines[:limit]
    return {
        "engine": "posix_find",
        "search_root": str(search_root),
        "count": len(matches),
        "matches": matches,
        "raw_output": output,
        "returncode": completed.returncode,
    }


def _collect_socket_snapshot() -> str:
    completed = subprocess.run(
        _RUNTIME.socket_snapshot_command(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (completed.stdout or "") + (completed.stderr or "")


def _analyze_socket_snapshot(raw_output: str) -> list[dict[str, str]]:
    parsed = _parse_netstat_live_connections(raw_output)
    results: list[dict[str, str]] = []
    for row in parsed:
        remote_ip = str(row.get("remote_ip", ""))
        risk, reason = _classify_remote_ip(remote_ip, str(row.get("remote", "")))
        enriched = {
            "protocol": str(row.get("protocol", "")),
            "local": str(row.get("local", "")),
            "remote": str(row.get("remote", "")),
            "remote_ip": remote_ip,
            "state": str(row.get("state", "")),
            "pid": str(row.get("pid", "")),
            "risk": risk,
            "reason": reason,
        }
        results.append(enriched)
    return results


def _classify_remote_ip(remote_ip: str, remote_raw: str) -> tuple[str, str]:
    if not remote_ip:
        return "low", "no_remote_ip"

    port = ""
    if ":" in remote_raw:
        port = remote_raw.rsplit(":", 1)[-1]

    high_risk_ports = {"23", "2323", "445", "3389", "5900", "21"}
    if port in high_risk_ports:
        return "high", f"sensitive_port:{port}"

    try:
        ip_obj = ipaddress.ip_address(remote_ip)
        if ip_obj.is_loopback:
            return "low", "loopback"
        if ip_obj.is_private:
            return "low", "private_network"
        if ip_obj.is_multicast or ip_obj.is_reserved:
            return "medium", "special_range"
        return "medium", "public_ip"
    except ValueError:
        return "medium", "non_ip_remote"
