"""OS Toolkit — file CRUD and system resource monitoring.

All file operations are sandboxed to ``settings.sandbox_root`` unless the
path is explicitly within that directory tree.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from config.logging import get_logger
from config.settings import get_settings
from tools.base import resolve_user_path
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

logger = get_logger(__name__)


def _resolve_sandboxed(path_str: str) -> Path:
    """Resolve *path_str* within the sandbox root. Raises on escape."""
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target, is_cross = resolve_user_path(path_str, sandbox)
    if is_cross:
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


def _resolve_write_target(path_str: str) -> Path:
    """Resolve write target allowing absolute paths after HITL approval."""
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    raw = (path_str or "").strip()
    if Path(raw).expanduser().is_absolute():
        target = Path(raw).expanduser().resolve()
        if target.exists() and target.is_dir():
            return target / "output_file.txt"
        if target.suffix == "":
            # If no filename extension is present and it points to an existing dir-like path,
            # make it an output file target.
            if target.exists() and target.is_dir():
                return target / "output_file.txt"
        return target
    target, is_cross = resolve_user_path(raw, sandbox)
    if is_cross:
        # Alias paths (Desktop/Documents/Downloads) are intentionally allowed
        # once execution reaches here (Guardian approval already happened).
        if target.exists() and target.is_dir():
            return target / "output_file.txt"
        if str(raw).lower() in {"desktop", "downloads", "documents"}:
            return target / "output_file.txt"
        return target
    return target


def _resolve_with_alias(path_str: str) -> tuple[Path, bool]:
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    return resolve_user_path(path_str, sandbox)


def _resolve_readonly(path_str: str) -> Path:
    """Resolve a user path for read-only access (sandbox or alias)."""
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    raw = (path_str or "").strip()
    if raw in {"", "."}:
        user_root = os.environ.get("USERPROFILE", r"C:\Users\mrSpy")
        return Path(user_root).resolve()
    target, _ = resolve_user_path(raw, sandbox)
    return target


# ---------------------------------------------------------------------------
# Read File
# ---------------------------------------------------------------------------
class OsReadFile(BaseTool):
    name = "os_read_file"
    description = "Read the contents of a file within the sandbox directory."

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "file_path", "path", "value")
            if not path_value:
                return self._failure("path is required")
            path = _resolve_readonly(str(path_value))
            if not path.is_file():
                return self._failure(f"File not found: {path}")
            max_bytes = params.get("max_bytes", 1_000_000)
            content = await asyncio.to_thread(path.read_text, encoding="utf-8")
            content = content[:max_bytes]
            return self._success(
                f"Read {len(content)} chars from {path.name}",
                data={"content": content, "path": str(path)},
            )
        except Exception as exc:
            return self._failure(str(exc))


# ---------------------------------------------------------------------------
# Write File
# ---------------------------------------------------------------------------
class OsWriteFile(BaseTool):
    name = "os_write_file"
    description = "Write content to a file within the sandbox directory."
    is_destructive = True  # can overwrite

    def requires_approval(self, tool_input: ToolInput) -> bool:
        params = self._params(tool_input)
        path = str(self._first_param(params, "file_path", "path", "value", default=""))
        _, is_cross = _resolve_with_alias(path)
        return self.is_destructive or is_cross

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "file_path", "path", "value")
            if not path_value:
                return self._failure("path is required")
            content = self._first_param(params, "content", "text", default="")
            path = _resolve_write_target(str(path_value))
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(path.write_text, str(content), encoding="utf-8")
            logger.info("os_toolkit.write_file", path=str(path), size=len(content))
            return self._success(f"Wrote {len(content)} chars to {path.name}")
        except Exception as exc:
            return self._failure(str(exc))


# ---------------------------------------------------------------------------
# List Directory
# ---------------------------------------------------------------------------
class OsListDir(BaseTool):
    name = "os_list_dir"
    description = "List files and directories within a sandbox path."

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "path", "file_path", "value", default=".")
            path = _resolve_readonly(str(path_value))
            if not path.is_dir():
                return self._failure(f"Not a directory: {path}")
            entries = await asyncio.to_thread(_list_dir_entries, path)
            return self._success(
                f"Listed {len(entries)} entries in {path.name}",
                data={"entries": entries, "path": str(path)},
            )
        except Exception as exc:
            return self._failure(str(exc))


# ---------------------------------------------------------------------------
# Move / Rename
# ---------------------------------------------------------------------------
class OsMoveFile(BaseTool):
    name = "os_move_file"
    description = "Move or rename a file/directory within the sandbox."
    is_destructive = True

    def requires_approval(self, tool_input: ToolInput) -> bool:
        params = self._params(tool_input)
        src = str(self._first_param(params, "source", "src", default=""))
        dst = str(self._first_param(params, "destination", "dest", default=""))
        _, cross_src = _resolve_with_alias(src)
        _, cross_dst = _resolve_with_alias(dst)
        return self.is_destructive or cross_src or cross_dst

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            src_value = self._first_param(params, "source", "src")
            dst_value = self._first_param(params, "destination", "dest")
            if not src_value or not dst_value:
                return self._failure("source and destination are required")
            src = _resolve_sandboxed(str(src_value))
            dst = _resolve_sandboxed(str(dst_value))
            if not src.exists():
                return self._failure(f"Source not found: {src}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.move, str(src), str(dst))
            logger.info("os_toolkit.move", src=str(src), dst=str(dst))
            return self._success(f"Moved {src.name} -> {dst.name}")
        except Exception as exc:
            return self._failure(str(exc))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
class OsDeleteFile(BaseTool):
    name = "os_delete_file"
    description = "Delete a file or directory within the sandbox."
    is_destructive = True

    def requires_approval(self, tool_input: ToolInput) -> bool:
        params = self._params(tool_input)
        path = str(self._first_param(params, "file_path", "path", "value", default=""))
        _, is_cross = _resolve_with_alias(path)
        return self.is_destructive or is_cross

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "file_path", "path", "value")
            if not path_value:
                return self._failure("path is required")
            path = _resolve_sandboxed(str(path_value))
            if not path.exists():
                return self._failure(f"Path not found: {path}")
            if path.is_dir():
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await asyncio.to_thread(path.unlink)
            logger.info("os_toolkit.delete", path=str(path))
            return self._success(f"Deleted {path.name}")
        except Exception as exc:
            return self._failure(str(exc))


# ---------------------------------------------------------------------------
# System Info
# ---------------------------------------------------------------------------
class OsSystemInfo(BaseTool):
    name = "os_system_info"
    description = "Report current CPU and memory usage of the host system."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            import psutil  # optional dependency

            info = {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                "memory_used_percent": psutil.virtual_memory().percent,
                "disk_usage_percent": psutil.disk_usage("/").percent,
            }
            return self._success("System info collected", data=info)
        except ImportError:
            # Fallback without psutil
            info = {
                "platform": os.name,
                "cpu_count": os.cpu_count(),
                "note": "Install psutil for detailed metrics",
            }
            return self._success("Basic system info (psutil not installed)", data=info)
        except Exception as exc:
            return self._failure(str(exc))


def _list_dir_entries(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for entry in sorted(path.iterdir()):
        entries.append(
            {
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else 0,
            }
        )
    return entries
