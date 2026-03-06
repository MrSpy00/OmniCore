"""Windows Power Toolkit — audio and window management."""

from __future__ import annotations

import asyncio
import subprocess

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class OsControlAudio(BaseTool):
    name = "os_control_audio"
    description = "Get/set/mute/unmute the Windows master volume."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", "command", default="get")).lower()
        level = self._first_param(params, "level", "volume", default=None)
        try:
            data = await asyncio.to_thread(_control_audio, action, level)
            return self._success("Audio command completed", data=data)
        except Exception as exc:
            return self._failure(str(exc))


class OsManageWindows(BaseTool):
    name = "os_manage_windows"
    description = "Minimize all windows, restore windows, or show desktop."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", "command", default="show_desktop")).lower()
        try:
            await asyncio.to_thread(_manage_windows, action)
            return self._success(f"Window action completed: {action}")
        except Exception as exc:
            return self._failure(str(exc))


def _control_audio(action: str, level: object | None) -> dict[str, object]:
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))

    if action == "mute":
        volume.SetMute(1, None)
    elif action == "unmute":
        volume.SetMute(0, None)
    elif action == "set":
        if level is None:
            raise ValueError("level is required for set")
        scalar = max(0.0, min(1.0, float(level) / 100.0))
        volume.SetMasterVolumeLevelScalar(scalar, None)

    current = int(volume.GetMasterVolumeLevelScalar() * 100)
    muted = bool(volume.GetMute())
    return {"volume_percent": current, "muted": muted}


def _manage_windows(action: str) -> None:
    cmd_map = {
        "minimize_all": "(New-Object -ComObject Shell.Application).MinimizeAll()",
        "restore_all": "(New-Object -ComObject Shell.Application).UndoMinimizeALL()",
        "show_desktop": "(New-Object -ComObject Shell.Application).MinimizeAll()",
    }
    command = cmd_map.get(action)
    if not command:
        raise ValueError("Unsupported action")
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=True, timeout=10)
