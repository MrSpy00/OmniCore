"""OS adapter abstractions for shell process bootstrap.

Provides a small Abstract Factory surface to avoid inline platform branching
inside tool implementations.
"""

from __future__ import annotations

import os
import platform
import shutil
from abc import ABC, abstractmethod


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
