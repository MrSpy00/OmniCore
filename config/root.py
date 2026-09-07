"""Shared project root resolution logic."""

from __future__ import annotations

import sys
from pathlib import Path


def resolve_project_root() -> Path:
    """Resolve the project root directory.

    For frozen (PyInstaller) builds, searches for .env next to the
    executable or in the current working directory.  For regular Python
    execution, returns the parent of this config package.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / ".env").exists():
            return exe_dir
        if (exe_dir.parent / ".env").exists():
            return exe_dir.parent
        if (Path.cwd() / ".env").exists():
            return Path.cwd()
        return exe_dir
    return Path(__file__).resolve().parent.parent
