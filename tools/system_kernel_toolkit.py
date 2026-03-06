"""System and kernel control toolkit."""

from __future__ import annotations

import asyncio
import subprocess
import winreg
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class SysManageServices(BaseTool):
    name = "sys_manage_services"
    description = "Start, stop, or restart a Windows service via sc.exe."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        service = str(self._first_param(params, "service", "name", default=""))
        action = str(self._first_param(params, "action", "command", default="status")).lower()
        if not service:
            return self._failure("service is required")
        try:
            output = await asyncio.to_thread(_service_command, service, action)
            return self._success(
                "Service command completed",
                data={"service": service, "action": action, "output": output},
            )
        except Exception as exc:
            return self._failure(str(exc))


class SysEditRegistry(BaseTool):
    name = "sys_edit_registry"
    description = "Read or write values in the Windows Registry."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        hive = str(self._first_param(params, "hive", default="HKCU"))
        key_path = str(self._first_param(params, "key_path", "path", default=""))
        value_name = str(self._first_param(params, "value_name", "name", default=""))
        action = str(self._first_param(params, "action", default="read")).lower()
        value = self._first_param(params, "value", "data", default="")
        if not key_path:
            return self._failure("key_path is required")
        try:
            result = await asyncio.to_thread(
                _registry_action, hive, key_path, value_name, action, value
            )
            return self._success("Registry operation completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class SysGetWifiPasswords(BaseTool):
    name = "sys_get_wifi_passwords"
    description = "Extract saved Wi-Fi profiles and their passwords using netsh."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            profiles = await asyncio.to_thread(_wifi_passwords)
            return self._success("Wi-Fi profiles extracted", data={"profiles": profiles})
        except Exception as exc:
            return self._failure(str(exc))


class SysControlHardware(BaseTool):
    name = "sys_control_hardware"
    description = "Adjust screen brightness or volume using native Windows commands."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        target = str(self._first_param(params, "target", "device", default="brightness")).lower()
        value = int(self._first_param(params, "value", "level", default=50) or 50)
        try:
            output = await asyncio.to_thread(_control_hardware, target, value)
            return self._success(
                "Hardware control completed",
                data={"target": target, "value": value, "output": output},
            )
        except Exception as exc:
            return self._failure(str(exc))


def _service_command(service: str, action: str) -> str:
    if action == "restart":
        subprocess.run(["sc", "stop", service], capture_output=True, text=True, timeout=15)
        completed = subprocess.run(
            ["sc", "start", service], capture_output=True, text=True, timeout=15
        )
        return completed.stdout + completed.stderr
    if action in {"start", "stop", "query"}:
        completed = subprocess.run(
            ["sc", action, service], capture_output=True, text=True, timeout=15
        )
        return completed.stdout + completed.stderr
    raise ValueError("Unsupported service action")


def _registry_action(
    hive_name: str,
    key_path: str,
    value_name: str,
    action: str,
    value: object,
) -> dict[str, object]:
    hive = getattr(
        winreg, "HKEY_CURRENT_USER" if hive_name.upper() == "HKCU" else "HKEY_LOCAL_MACHINE"
    )
    if action == "read":
        with winreg.OpenKey(hive, key_path) as key:
            data, reg_type = winreg.QueryValueEx(key, value_name)
            return {"value": data, "type": reg_type}
    if action == "write":
        with winreg.CreateKey(hive, key_path) as key:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, str(value))
            return {"value": value, "written": True}
    raise ValueError("Unsupported registry action")


def _wifi_passwords() -> list[dict[str, str]]:
    profiles_output = subprocess.run(
        ["netsh", "wlan", "show", "profiles"],
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    profiles = []
    for line in profiles_output.splitlines():
        if "All User Profile" not in line:
            continue
        name = line.split(":", 1)[1].strip()
        detail = subprocess.run(
            ["netsh", "wlan", "show", "profile", name, "key=clear"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
        password = ""
        for detail_line in detail.splitlines():
            if "Key Content" in detail_line:
                password = detail_line.split(":", 1)[1].strip()
                break
        profiles.append({"ssid": name, "password": password})
    return profiles


def _control_hardware(target: str, value: int) -> str:
    if target == "brightness":
        command = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{value})"
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.stdout + completed.stderr
    if target == "volume":
        command = (
            f"(New-Object -ComObject WScript.Shell).SendKeys([char]175 * {max(1, value // 2)})"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return completed.stdout + completed.stderr
    raise ValueError("Unsupported hardware target")
