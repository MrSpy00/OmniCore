"""OS adapter abstractions for shell process bootstrap.

Provides a small Abstract Factory surface to avoid inline platform branching
inside tool implementations.
"""

from __future__ import annotations

import os
import platform
import shutil
from abc import ABC, abstractmethod
from pathlib import Path


class BaseShellAdapter(ABC):
    """Factory interface for shell command argv creation."""

    @abstractmethod
    def build_command(self, command: str, preferred_shell: str = "") -> tuple[list[str], str]:
        """Return shell argv and shell name."""


class WindowsShellAdapter(BaseShellAdapter):
    """Windows shell adapter using PowerShell/CMD."""

    def build_command(self, command: str, preferred_shell: str = "") -> tuple[list[str], str]:
        pref = (preferred_shell or "").strip().lower()
        if pref == "cmd":
            comspec = os.environ.get("COMSPEC") or "cmd.exe"
            return [comspec, "/d", "/s", "/c", command], "cmd"

        powershell = shutil.which("powershell") or "powershell"
        ps_command = (
            "$OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new(); "
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            f"{command}"
        )
        return (
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ],
            "powershell",
        )


class PosixShellAdapter(BaseShellAdapter):
    """POSIX shell adapter using zsh/bash/sh."""

    def build_command(self, command: str, preferred_shell: str = "") -> tuple[list[str], str]:
        pref = (preferred_shell or "").strip().lower()
        if pref in {"zsh", "bash", "sh"}:
            shell_path = shutil.which(pref)
            if shell_path:
                return [shell_path, "-lc", command], pref

        if platform.system().lower() == "darwin":
            zsh = shutil.which("zsh")
            if zsh:
                return [zsh, "-lc", command], "zsh"
            bash = shutil.which("bash") or "/bin/bash"
            return [bash, "-lc", command], "bash"

        bash = shutil.which("bash")
        if bash:
            return [bash, "-lc", command], "bash"
        sh = shutil.which("sh") or "/bin/sh"
        return [sh, "-lc", command], "sh"


class ShellAdapterFactory:
    """Lazy OS adapter factory."""

    _adapter: BaseShellAdapter | None = None

    @classmethod
    def get_adapter(cls) -> BaseShellAdapter:
        if cls._adapter is None:
            cls._adapter = WindowsShellAdapter() if os.name == "nt" else PosixShellAdapter()
        return cls._adapter


class BaseRuntimeAdapter(ABC):
    """Runtime OS abstraction for non-shell platform decisions."""

    @property
    @abstractmethod
    def is_windows(self) -> bool:
        """Return True when running on Windows."""

    @abstractmethod
    def ping_count_flag(self) -> str:
        """Return platform-specific ping count flag."""

    @abstractmethod
    def default_disk_usage_path(self) -> str:
        """Return default root path for disk usage metrics."""

    @abstractmethod
    def default_search_root(self) -> Path:
        """Return default filesystem root for deep search."""

    @abstractmethod
    def temp_directories(self) -> list[str]:
        """Return temp directories suitable for cleanup operations."""

    @abstractmethod
    def socket_snapshot_command(self) -> list[str]:
        """Return argv for socket snapshot command."""


class WindowsRuntimeAdapter(BaseRuntimeAdapter):
    @property
    def is_windows(self) -> bool:
        return True

    def ping_count_flag(self) -> str:
        return "-n"

    def default_disk_usage_path(self) -> str:
        return os.environ.get("SystemDrive", "C:") + "\\"

    def default_search_root(self) -> Path:
        return Path("C:\\")

    def temp_directories(self) -> list[str]:
        return [os.getenv("TEMP", ""), r"C:\Windows\Temp"]

    def socket_snapshot_command(self) -> list[str]:
        return ["netstat", "-ano"]


class PosixRuntimeAdapter(BaseRuntimeAdapter):
    @property
    def is_windows(self) -> bool:
        return False

    def ping_count_flag(self) -> str:
        return "-c"

    def default_disk_usage_path(self) -> str:
        return "/"

    def default_search_root(self) -> Path:
        return Path("/")

    def temp_directories(self) -> list[str]:
        return [os.getenv("TEMP", ""), "/tmp"]

    def socket_snapshot_command(self) -> list[str]:
        return ["netstat", "-tunap"]


class RuntimeAdapterFactory:
    """Lazy runtime adapter factory."""

    _adapter: BaseRuntimeAdapter | None = None

    @classmethod
    def get_adapter(cls) -> BaseRuntimeAdapter:
        if cls._adapter is None:
            cls._adapter = WindowsRuntimeAdapter() if os.name == "nt" else PosixRuntimeAdapter()
        return cls._adapter


def runtime_adapter() -> BaseRuntimeAdapter:
    """Convenience accessor for runtime adapter singleton."""
    return RuntimeAdapterFactory.get_adapter()


def is_windows_platform() -> bool:
    """Return True when current runtime adapter targets Windows."""
    return runtime_adapter().is_windows
