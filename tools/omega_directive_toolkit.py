"""Omega Directive toolkit for hybrid fallback, diagnostics, and hardening."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from models.tools import ToolInput
from tools.base import BaseTool, force_window_foreground, resolve_user_path


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _home_for_inventory() -> Path:
    return resolve_user_path(".")[0]


class SysWmiHardwareAudit(BaseTool):
    name = "sys_wmi_hardware_audit"
    description = "Run deep hardware audit via WMI/WMIC (Windows) or platform fallback."

    async def execute(self, tool_input: ToolInput):
        try:
            data = await asyncio.to_thread(_hardware_audit_sync)
            return self._success("Hardware audit completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class NetPacketSniffer(BaseTool):
    name = "net_packet_sniffer"
    description = "Capture packet summary using tshark/tcpdump/pktmon backends."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        duration = int(self._first_param(params, "duration", "seconds", default=8) or 8)
        packet_limit = int(self._first_param(params, "packet_limit", "count", default=120) or 120)
        interface = str(self._first_param(params, "interface", "iface", default="") or "")
        output = str(
            self._first_param(
                params,
                "output_path",
                "path",
                default=(Path(tempfile.gettempdir()) / "omnicore_packet_capture.txt"),
            )
        )
        try:
            capture_path = resolve_user_path(output)[0]
            capture_path.parent.mkdir(parents=True, exist_ok=True)
            result = await asyncio.to_thread(
                _packet_sniffer_sync,
                capture_path,
                max(1, duration),
                max(1, packet_limit),
                interface,
            )
            return self._success("Packet capture completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class GuiAutonomousExplorer(BaseTool):
    name = "gui_autonomous_explorer"
    description = "Hybrid GUI fallback: opens target in visible browser and foregrounds it."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", default="") or "").strip()
        query = str(self._first_param(params, "query", "goal", "target", default="") or "").strip()
        max_steps = int(self._first_param(params, "max_steps", default=4) or 4)

        if not url and not query:
            return self._failure("url or query is required")

        try:
            data = await asyncio.to_thread(
                _gui_autonomous_explore_sync, url, query, max(1, max_steps)
            )
            return self._success("GUI autonomous explorer completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class DevAutoDebugger(BaseTool):
    name = "dev_auto_debugger"
    description = "Auto triage failing command/test and provide structured debug hints."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        command = str(
            self._first_param(params, "command", "cmd", default="uv run pytest -v") or ""
        ).strip()
        cwd_raw = str(self._first_param(params, "cwd", "path", default=".") or ".")
        timeout = int(self._first_param(params, "timeout", default=180) or 180)
        if not command:
            return self._failure("command is required")

        try:
            cwd = resolve_user_path(cwd_raw)[0]
            data = await asyncio.to_thread(_auto_debug_sync, command, cwd, max(10, timeout))
            status = data.get("status", "ok")
            if status == "failed":
                return self._failure(json.dumps(data, ensure_ascii=True))
            return self._success("Auto debugger completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class OsRegistryDeepTweak(BaseTool):
    name = "os_registry_deep_tweak"
    description = "Read/write/delete Windows Registry values with strict guardrails."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", default="read") or "read").lower()
        hive = str(
            self._first_param(params, "hive", default="HKEY_CURRENT_USER") or "HKEY_CURRENT_USER"
        )
        key_path = str(self._first_param(params, "key_path", "path", default="") or "")
        value_name = str(self._first_param(params, "value_name", "name", default="") or "")
        value_data = self._first_param(params, "value_data", "value", default="")
        value_type = str(
            self._first_param(params, "value_type", "type", default="REG_SZ") or "REG_SZ"
        )

        if not key_path:
            return self._failure("key_path is required")

        try:
            result = await asyncio.to_thread(
                _registry_tweak_sync,
                action,
                hive,
                key_path,
                value_name,
                value_data,
                value_type,
            )
            return self._success("Registry operation completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class SysPlatformProbe(BaseTool):
    name = "sys_platform_probe"
    description = "Collect cross-platform runtime and shell/backend availability map."

    async def execute(self, tool_input: ToolInput):
        try:
            data = await asyncio.to_thread(_platform_probe_sync)
            return self._success("Platform probe completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class NetConnectionKillSwitch(BaseTool):
    name = "net_connection_kill_switch"
    description = "Kill connections by remote host or port using native OS commands."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        host = str(self._first_param(params, "host", "remote_host", default="") or "")
        port = int(self._first_param(params, "port", default=0) or 0)
        if not host and port <= 0:
            return self._failure("host or port is required")
        try:
            data = await asyncio.to_thread(_kill_connections_sync, host, port)
            return self._success("Connection kill-switch executed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class GuiForegroundGuard(BaseTool):
    name = "gui_foreground_guard"
    description = "Assert/force window foreground by title and verify active window text."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        title = str(self._first_param(params, "window_title", "title", default="") or "")
        if not title:
            return self._failure("window_title is required")
        try:
            data = await asyncio.to_thread(_foreground_guard_sync, title)
            if not data.get("activated"):
                return self._failure(json.dumps(data, ensure_ascii=True))
            return self._success("Foreground guard completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class DevDependencyAudit(BaseTool):
    name = "dev_dependency_audit"
    description = "Audit dependencies (uv pip check / pip check) and emit actionable report."
    is_destructive = True

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        cwd_raw = str(self._first_param(params, "cwd", "path", default=".") or ".")
        try:
            cwd = resolve_user_path(cwd_raw)[0]
            data = await asyncio.to_thread(_dependency_audit_sync, cwd)
            if data.get("status") == "failed":
                return self._failure(json.dumps(data, ensure_ascii=True))
            return self._success("Dependency audit completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class OsCrossRootInventory(BaseTool):
    name = "os_cross_root_inventory"
    description = "Inventory selected roots across drives/filesystems with size and counts."

    async def execute(self, tool_input: ToolInput):
        params = self._params(tool_input)
        roots_raw = self._first_param(params, "roots", default=None)
        max_entries = int(self._first_param(params, "max_entries", default=2000) or 2000)
        try:
            data = await asyncio.to_thread(
                _cross_root_inventory_sync, roots_raw, max(100, max_entries)
            )
            return self._success("Cross-root inventory completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


def _hardware_audit_sync() -> dict[str, object]:
    if os.name == "nt":
        return _hardware_audit_windows_sync()
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "hostname": socket.gethostname(),
        "note": "WMI only available on Windows; returned cross-platform fallback.",
    }


def _hardware_audit_windows_sync() -> dict[str, object]:
    queries = {
        "cpu": [
            "wmic",
            "cpu",
            "get",
            "Name,NumberOfCores,NumberOfLogicalProcessors",
            "/format:list",
        ],
        "bios": [
            "wmic",
            "bios",
            "get",
            "SerialNumber,Manufacturer,SMBIOSBIOSVersion",
            "/format:list",
        ],
        "baseboard": [
            "wmic",
            "baseboard",
            "get",
            "Manufacturer,Product,SerialNumber",
            "/format:list",
        ],
        "memory": [
            "wmic",
            "memorychip",
            "get",
            "Capacity,Speed,Manufacturer,PartNumber",
            "/format:list",
        ],
        "gpu": [
            "wmic",
            "path",
            "win32_VideoController",
            "get",
            "Name,DriverVersion,AdapterRAM",
            "/format:list",
        ],
    }
    out: dict[str, object] = {"platform": platform.platform()}
    for key, cmd in queries.items():
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        out[key] = {
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }
    return out


def _packet_sniffer_sync(
    capture_path: Path,
    duration: int,
    packet_limit: int,
    interface: str,
) -> dict[str, object]:
    if _command_exists("tshark"):
        cmd = [
            "tshark",
            "-a",
            f"duration:{duration}",
            "-c",
            str(packet_limit),
            "-q",
            "-z",
            "io,stat,1",
        ]
        if interface:
            cmd.extend(["-i", interface])
        completed = subprocess.run(
            cmd, capture_output=True, text=True, timeout=max(20, duration + 15)
        )
        capture_path.write_text(
            (completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8"
        )
        return {
            "backend": "tshark",
            "path": str(capture_path),
            "returncode": completed.returncode,
            "stdout_preview": (completed.stdout or "")[:3000],
            "stderr_preview": (completed.stderr or "")[:1200],
        }

    if _command_exists("tcpdump"):
        cmd = ["tcpdump", "-n", "-c", str(packet_limit)]
        if interface:
            cmd.extend(["-i", interface])
        completed = subprocess.run(
            cmd, capture_output=True, text=True, timeout=max(20, duration + 15)
        )
        capture_path.write_text(
            (completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8"
        )
        return {
            "backend": "tcpdump",
            "path": str(capture_path),
            "returncode": completed.returncode,
            "stdout_preview": (completed.stdout or "")[:3000],
            "stderr_preview": (completed.stderr or "")[:1200],
        }

    if os.name == "nt" and _command_exists("pktmon"):
        cmd = ["pktmon", "start", "--etw", "--capture", "--pkt-size", "128"]
        first = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        time.sleep(min(duration, 15))
        stop = subprocess.run(["pktmon", "stop"], capture_output=True, text=True, timeout=20)
        payload = (
            "pktmon backend run\n"
            f"start rc={first.returncode}\n{first.stdout}\n{first.stderr}\n"
            f"stop rc={stop.returncode}\n{stop.stdout}\n{stop.stderr}\n"
        )
        capture_path.write_text(payload, encoding="utf-8")
        return {
            "backend": "pktmon",
            "path": str(capture_path),
            "start_returncode": first.returncode,
            "stop_returncode": stop.returncode,
            "stdout_preview": payload[:3000],
        }

    raise RuntimeError("No supported sniffer backend found (tshark/tcpdump/pktmon)")


def _gui_autonomous_explore_sync(url: str, query: str, max_steps: int) -> dict[str, object]:
    steps: list[dict[str, str]] = []
    target_url = url.strip()
    if not target_url and query:
        if query.startswith("http://") or query.startswith("https://"):
            target_url = query
        else:
            encoded = query.replace(" ", "+")
            target_url = f"https://www.google.com/search?q={encoded}"

    if not target_url:
        raise RuntimeError("No navigable URL resolved")

    import webbrowser

    import pyautogui

    webbrowser.open_new_tab(target_url)
    steps.append({"action": "open_new_tab", "target": target_url})

    force = force_window_foreground("Chrome")
    if not force.get("activated"):
        force = force_window_foreground("Edge")
    if not force.get("activated"):
        force = force_window_foreground("Firefox")
    if not force.get("activated"):
        force = force_window_foreground("Browser")
    steps.append({"action": "force_foreground", "target": json.dumps(force, ensure_ascii=True)})

    # Human-like fallback actions: search bar focus + type + enter + settle.
    try:
        pyautogui.hotkey("ctrl", "l")
        steps.append({"action": "hotkey", "target": "ctrl+l"})
        pyautogui.write(target_url, interval=0.01)
        steps.append({"action": "type", "target": target_url})
        pyautogui.press("enter")
        steps.append({"action": "press", "target": "enter"})
        time.sleep(1.5)
    except Exception as exc:
        steps.append({"action": "input_sequence_error", "target": str(exc)})

    return {
        "url": target_url,
        "steps": steps[:max_steps],
        "foreground": force,
    }


def _auto_debug_sync(command: str, cwd: Path, timeout: int) -> dict[str, object]:
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd),
    )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    merged = f"{stdout}\n{stderr}".lower()

    hints: list[str] = []
    if "modulenotfounderror" in merged:
        hints.append("Dependency missing: run 'uv sync' then retry.")
    if "permission denied" in merged:
        hints.append("Permission issue: retry elevated shell or adjust target path ACL.")
    if "timed out" in merged or "timeout" in merged:
        hints.append("Timeout detected: increase timeout or isolate slow external calls.")
    if "assert" in merged and "failed" in merged:
        hints.append("Test assertion failure: inspect failing test diff and expected fixtures.")
    if not hints and completed.returncode != 0:
        hints.append("General failure: inspect stderr first, then rerun with verbose/debug flags.")

    payload = {
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "command": command,
        "cwd": str(cwd),
        "stdout_preview": stdout[:4000],
        "stderr_preview": stderr[:4000],
        "hints": hints,
    }
    return payload


def _registry_tweak_sync(
    action: str,
    hive: str,
    key_path: str,
    value_name: str,
    value_data,
    value_type: str,
) -> dict[str, object]:
    if os.name != "nt":
        raise RuntimeError("Registry operations are Windows-only")

    import winreg  # type: ignore[import-not-found]

    hive_map = {
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
        "HKCR": winreg.HKEY_CLASSES_ROOT,
    }
    reg_hive = hive_map.get(hive.upper())
    if reg_hive is None:
        raise RuntimeError(f"Unsupported hive: {hive}")

    safe_prefixes = (
        r"Software\\",
        r"SOFTWARE\\",
        r"Control Panel\\",
        r"Environment",
    )
    if not key_path.startswith(safe_prefixes):
        raise RuntimeError("Blocked by guardrail: key_path must be under user-safe prefixes")

    if action == "read":
        with winreg.OpenKey(reg_hive, key_path, 0, winreg.KEY_READ) as key:
            if value_name:
                value, reg_type = winreg.QueryValueEx(key, value_name)
                return {
                    "action": action,
                    "value_name": value_name,
                    "value": value,
                    "reg_type": reg_type,
                }
            values = []
            index = 0
            while True:
                try:
                    name, value, reg_type = winreg.EnumValue(key, index)
                    values.append({"name": name, "value": value, "reg_type": reg_type})
                    index += 1
                except OSError:
                    break
            return {"action": action, "values": values}

    if action in {"write", "set"}:
        type_map = {
            "REG_SZ": winreg.REG_SZ,
            "REG_DWORD": winreg.REG_DWORD,
            "REG_QWORD": winreg.REG_QWORD,
            "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
        }
        reg_type = type_map.get(value_type.upper())
        if reg_type is None:
            raise RuntimeError(f"Unsupported value_type: {value_type}")
        with winreg.CreateKeyEx(reg_hive, key_path, 0, winreg.KEY_SET_VALUE) as key:
            write_value = value_data
            if reg_type in (winreg.REG_DWORD, winreg.REG_QWORD):
                write_value = int(value_data)
            else:
                write_value = str(value_data)
            winreg.SetValueEx(key, value_name, 0, reg_type, write_value)
        return {"action": action, "written": True, "value_name": value_name}

    if action == "delete":
        with winreg.OpenKey(reg_hive, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value_name)
        return {"action": action, "deleted": True, "value_name": value_name}

    raise RuntimeError("Unsupported action. Use read|write|delete")


def _platform_probe_sync() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "commands": {
            "tshark": _command_exists("tshark"),
            "tcpdump": _command_exists("tcpdump"),
            "pktmon": _command_exists("pktmon"),
            "uv": _command_exists("uv"),
            "python": _command_exists("python"),
            "powershell": _command_exists("powershell"),
            "pwsh": _command_exists("pwsh"),
        },
    }


def _kill_connections_sync(host: str, port: int) -> dict[str, object]:
    if os.name == "nt":
        base = ["powershell", "-NoProfile", "-Command"]
        kill_expr = (
            "| Select-Object -ExpandProperty OwningProcess "
            "| ForEach-Object { Stop-Process -Id $_ -Force }"
        )
        if host and port > 0:
            script = (
                f"Get-NetTCPConnection -State Established "
                f"-RemoteAddress '{host}' -RemotePort {port} "
                f"{kill_expr}"
            )
        elif host:
            script = f"Get-NetTCPConnection -State Established -RemoteAddress '{host}' {kill_expr}"
        else:
            script = f"Get-NetTCPConnection -State Established -RemotePort {port} {kill_expr}"
        completed = subprocess.run(base + [script], capture_output=True, text=True, timeout=40)
        return {
            "backend": "powershell",
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[:4000],
            "stderr": (completed.stderr or "")[:2000],
            "host": host,
            "port": port,
        }

    cmd = ["sh", "-lc"]
    if host and port > 0:
        expr = f"ss -tpn | grep '{host}:{port}' | awk '{{print $7}}'"
    elif host:
        expr = f"ss -tpn | grep '{host}' | awk '{{print $7}}'"
    else:
        expr = f"ss -tpn | grep ':{port} ' | awk '{{print $7}}'"
    shell_script = (
        f"pids=$({expr} | sed -E 's/.*pid=([0-9]+).*/\\1/' | grep -E '^[0-9]+$' | sort -u); "
        'for p in $pids; do kill -9 $p; done; echo "$pids"'
    )
    completed = subprocess.run(cmd + [shell_script], capture_output=True, text=True, timeout=40)
    return {
        "backend": "ss+kill",
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[:4000],
        "stderr": (completed.stderr or "")[:2000],
        "host": host,
        "port": port,
    }


def _foreground_guard_sync(title: str) -> dict[str, object]:
    result = force_window_foreground(title)
    payload: dict[str, object] = {
        "requested_title": title,
        "activated": bool(result.get("activated")),
    }
    payload.update(result)
    return payload


def _dependency_audit_sync(cwd: Path) -> dict[str, object]:
    commands: list[list[str]] = []
    if _command_exists("uv"):
        commands.append(["uv", "pip", "check"])
    commands.append(["python", "-m", "pip", "check"])

    reports: list[dict[str, object]] = []
    for cmd in commands:
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                cwd=str(cwd),
            )
            reports.append(
                {
                    "command": " ".join(cmd),
                    "returncode": completed.returncode,
                    "stdout": (completed.stdout or "")[:3000],
                    "stderr": (completed.stderr or "")[:2000],
                }
            )
        except Exception as exc:
            reports.append({"command": " ".join(cmd), "returncode": -1, "error": str(exc)})

    failed = False
    for item in reports:
        rc_raw = item.get("returncode", 1)
        try:
            rc = int(rc_raw)  # type: ignore[arg-type]
        except Exception:
            rc = 1
        if rc != 0:
            failed = True
            break
    return {
        "status": "failed" if failed else "ok",
        "cwd": str(cwd),
        "reports": reports,
    }


def _cross_root_inventory_sync(roots_raw, max_entries: int) -> dict[str, object]:
    roots: list[Path] = []

    if isinstance(roots_raw, list):
        for item in roots_raw:
            roots.append(resolve_user_path(str(item))[0])
    elif isinstance(roots_raw, str) and roots_raw.strip():
        parts = [part.strip() for part in roots_raw.split(",") if part.strip()]
        for part in parts:
            roots.append(resolve_user_path(part)[0])

    if not roots:
        if os.name == "nt":
            for drive in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                root = Path(f"{drive}:\\")
                if root.exists():
                    roots.append(root)
        else:
            roots = [Path("/"), _home_for_inventory()]

    inventory: list[dict[str, object]] = []
    for root in roots:
        if not root.exists():
            inventory.append({"root": str(root), "exists": False})
            continue

        file_count = 0
        dir_count = 0
        sampled = 0
        for path in root.rglob("*"):
            if sampled >= max_entries:
                break
            sampled += 1
            if path.is_dir():
                dir_count += 1
            elif path.is_file():
                file_count += 1

        disk = shutil.disk_usage(root)
        inventory.append(
            {
                "root": str(root),
                "exists": True,
                "sampled_entries": sampled,
                "files_in_sample": file_count,
                "dirs_in_sample": dir_count,
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
            }
        )

    return {"roots": inventory, "max_entries_per_root": max_entries}
