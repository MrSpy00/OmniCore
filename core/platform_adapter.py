"""Unified OS Platform Adapter — Cross-platform abstraction layer for Windows, Linux, and macOS."""

from __future__ import annotations

import platform
import sys
from typing import Any


class PlatformAdapter:
    """Provides unified system abstraction across OS platforms."""

    @staticmethod
    def get_os_type() -> str:
        if sys.platform == "win32":
            return "windows"
        if sys.platform == "darwin":
            return "macos"
        return "linux"

    @staticmethod
    def get_system_summary() -> dict[str, Any]:
        return {
            "os_type": PlatformAdapter.get_os_type(),
            "architecture": platform.architecture()[0],
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "platform_release": platform.release(),
        }

    @staticmethod
    def get_default_shell() -> str:
        os_type = PlatformAdapter.get_os_type()
        if os_type == "windows":
            return "powershell"
        return "bash"
