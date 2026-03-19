"""Windows Power Toolkit — audio and window management."""

from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any

import pyautogui

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
    if os.name != "nt":
        raise RuntimeError("os_control_audio is Windows-only")

    level_value: float | None = None
    try:
        if level is not None:
            level_value = float(str(level))
    except Exception:
        level_value = None

    from ctypes import POINTER
    from ctypes import cast as c_cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    devices = AudioUtilities.GetSpeakers()
    if devices is None:
        raise RuntimeError("No default speaker endpoint found")
    devices_any: Any = devices
    interface = devices_any.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = c_cast(interface, POINTER(IAudioEndpointVolume))
    volume_any: Any = volume

    if action == "mute":
        volume_any.SetMute(1, None)
    elif action == "unmute":
        volume_any.SetMute(0, None)
    elif action == "set":
        if level_value is None:
            raise ValueError("level is required for set")
        scalar = max(0.0, min(1.0, float(level_value) / 100.0))
        volume_any.SetMasterVolumeLevelScalar(scalar, None)

    current = int(volume_any.GetMasterVolumeLevelScalar() * 100)
    muted = bool(volume_any.GetMute())
    return {"volume_percent": current, "muted": muted}


def _manage_windows(action: str) -> None:
    if os.name != "nt":
        raise RuntimeError("os_manage_windows is Windows-only")

    if action in {"minimize_all", "show_desktop"}:
        pyautogui.hotkey("win", "d")
        return
    if action == "restore_all":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(New-Object -ComObject Shell.Application).UndoMinimizeALL()",
            ],
            check=True,
            timeout=10,
        )
        return
    raise ValueError("Unsupported action")
