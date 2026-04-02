"""OS Toolkit — file CRUD and system resource monitoring."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path
from tools.os_adapters import runtime_adapter

logger = get_logger(__name__)
_RUNTIME = runtime_adapter()


def _home_root() -> Path:
    return resolve_user_path(".")[0]


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _require_destructive_boundary(path: Path) -> None:
    root = _home_root()
    if not _is_within_root(path, root):
        raise PermissionError(
            f"Destructive operation is only allowed under user root: {root} (requested: {path})"
        )


def _resolve_sandboxed(path_str: str) -> Path:
    """Resolve a path directly on the host OS."""
    target, _ = resolve_user_path(path_str)
    return target


def _resolve_write_target(path_str: str) -> Path:
    raw = (path_str or "").strip()
    target, _ = resolve_user_path(raw)
    if target.exists() and target.is_dir():
        return target / "output_file.txt"
    if str(raw).strip().lower() in {"desktop", "downloads", "documents"}:
        return target / "output_file.txt"
    return target


def _resolve_with_alias(path_str: str) -> tuple[Path, bool]:
    return resolve_user_path(path_str)


def _resolve_readonly(path_str: str) -> Path:
    """Resolve a user path for host OS read access."""
    raw = (path_str or "").strip()
    target, _ = resolve_user_path(raw)
    return target


# ---------------------------------------------------------------------------
# Read File
# ---------------------------------------------------------------------------
class OsReadFile(BaseTool):
    name = "os_read_file"
    description = "Read the contents of a file on the host OS."

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
    description = "Write content to a file on the host OS."
    is_destructive = True  # can overwrite

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "file_path", "path", "value")
            if not path_value:
                return self._failure("path is required")
            content = self._first_param(params, "content", "text", default="")
            path = _resolve_write_target(str(path_value))
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                await asyncio.to_thread(path.write_text, str(content), encoding="utf-8")
            except PermissionError as exc:
                elevation_result = await asyncio.to_thread(
                    _attempt_windows_elevation_write,
                    path,
                    str(content),
                )
                if not elevation_result.get("ok"):
                    elevate_error = elevation_result.get("error") or elevation_result
                    return self._failure(
                        f"Permission denied and elevation failed: {exc}; {elevate_error}"
                    )
            if not path.exists() or not path.is_file():
                return self._failure(f"Write verification failed: {path}")

            try:
                stat = await asyncio.to_thread(path.stat)
                bytes_written = int(stat.st_size)
            except Exception:
                bytes_written = len(str(content).encode("utf-8"))

            logger.info("os_toolkit.write_file", path=str(path), size=len(content))
            return self._success(
                f"Wrote {len(content)} chars to {path.name}",
                data={"path": str(path), "bytes_written": bytes_written},
            )
        except Exception as exc:
            return self._failure(str(exc))


# ---------------------------------------------------------------------------
# List Directory
# ---------------------------------------------------------------------------
class OsListDir(BaseTool):
    name = "os_list_dir"
    description = "List files and directories on the host OS."

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
    description = "Move or rename a file or directory on the host OS."
    is_destructive = True

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

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
    description = "Delete a file or directory on the host OS."
    is_destructive = True

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "file_path", "path", "value")
            dry_run = bool(self._first_param(params, "dry_run", default=True))
            if not path_value:
                return self._failure("path is required")
            path = _resolve_sandboxed(str(path_value))
            if not path.exists():
                return self._failure(f"Path not found: {path}")

            _require_destructive_boundary(path)

            if dry_run:
                return self._success(
                    "Dry-run completed; delete not executed",
                    data={
                        "dry_run": True,
                        "path": str(path),
                        "is_dir": path.is_dir(),
                        "exists": path.exists(),
                    },
                )

            if path.is_dir():
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await asyncio.to_thread(path.unlink)
            logger.info("os_toolkit.delete", path=str(path))
            return self._success(f"Deleted {path.name}")
        except Exception as exc:
            return self._failure(str(exc))


class OsSafeDelete(BaseTool):
    name = "os_safe_delete"
    description = "Safely delete by quarantine move or wipe mode on the host OS."
    is_destructive = True

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "file_path", "path", "value")
            mode = str(self._first_param(params, "mode", "action", default="quarantine")).lower()
            dry_run = bool(self._first_param(params, "dry_run", default=False))
            if not path_value:
                return self._failure("path is required")
            if mode not in {"quarantine", "wipe"}:
                return self._failure("mode must be quarantine or wipe")

            path = _resolve_sandboxed(str(path_value))
            if not path.exists():
                return self._failure(f"Path not found: {path}")

            _require_destructive_boundary(path)

            if dry_run:
                return self._success(
                    "Dry-run completed; safe-delete not executed",
                    data={
                        "dry_run": True,
                        "mode": mode,
                        "path": str(path),
                        "is_dir": path.is_dir(),
                        "size": path.stat().st_size if path.is_file() else 0,
                    },
                )

            result = await asyncio.to_thread(_safe_delete_path, path, mode)
            return self._success("Safe delete completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class OsSetProcessPriority(BaseTool):
    name = "os_set_process_priority"
    description = "Set process priority safely across Windows/macOS/Linux."
    is_destructive = True

    def requires_approval(self, tool_input: ToolInput) -> bool:
        return self.is_destructive

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            pid_raw = self._first_param(params, "pid", "process_id", "id")
            level = str(self._first_param(params, "level", "priority", default="normal")).lower()
            if pid_raw is None:
                return self._failure("pid is required")

            try:
                import psutil
            except ImportError:
                return self._failure("psutil is required for os_set_process_priority")

            pid = int(pid_raw)
            result = await asyncio.to_thread(_set_process_priority, psutil, pid, level)
            return self._success("Process priority updated", data=result)
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
                "disk_usage_percent": psutil.disk_usage(_disk_usage_path()).percent,
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
        try:
            size = entry.stat().st_size if entry.is_file() else 0
        except OSError:
            size = 0
        entries.append(
            {
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": size,
            }
        )
    return entries


def _disk_usage_path() -> str:
    return _RUNTIME.default_disk_usage_path()


def _safe_delete_path(path: Path, mode: str) -> dict[str, object]:
    if mode == "quarantine":
        home = Path(os.environ.get("USERPROFILE") or Path.home())
        trash_dir = home / ".omnicore_trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        target = trash_dir / f"{path.name}.{int(time.time())}"
        shutil.move(str(path), str(target))
        return {
            "mode": "quarantine",
            "source": str(path),
            "target": str(target),
            "exists_in_trash": target.exists(),
        }

    if path.is_dir():
        shutil.rmtree(path)
        return {
            "mode": "wipe",
            "target": str(path),
            "deleted": not path.exists(),
        }

    _wipe_file_contents(path)
    path.unlink(missing_ok=True)
    return {
        "mode": "wipe",
        "target": str(path),
        "deleted": not path.exists(),
    }


def _wipe_file_contents(path: Path, chunk_size: int = 1024 * 1024) -> None:
    size = path.stat().st_size
    if size <= 0:
        return
    with path.open("r+b") as handle:
        remaining = size
        zero_chunk = b"\x00" * min(chunk_size, max(1, size))
        while remaining > 0:
            write_size = min(len(zero_chunk), remaining)
            handle.write(zero_chunk[:write_size])
            remaining -= write_size
        handle.flush()
        os.fsync(handle.fileno())


def _set_process_priority(psutil_module, pid: int, level: str) -> dict[str, object]:
    process = psutil_module.Process(pid)
    before = process.nice()

    if _RUNTIME.is_windows:
        win_map = {
            "low": psutil_module.IDLE_PRIORITY_CLASS,
            "normal": psutil_module.NORMAL_PRIORITY_CLASS,
            "high": psutil_module.HIGH_PRIORITY_CLASS,
            "realtime": psutil_module.REALTIME_PRIORITY_CLASS,
        }
        if level not in win_map:
            raise ValueError("level must be low, normal, high, or realtime")
        process.nice(win_map[level])
    else:
        unix_map = {"low": 10, "normal": 0, "high": -5}
        if level not in unix_map:
            raise ValueError("level must be low, normal, or high")
        process.nice(unix_map[level])

    after = process.nice()
    return {
        "pid": pid,
        "level": level,
        "previous": str(before),
        "current": str(after),
    }


def _attempt_windows_elevation_write(path: Path, content: str) -> dict[str, object]:
    """Attempt elevated write by relaunching python with RunAs."""
    escaped_path = str(path).replace("'", "''")
    escaped_content = content.replace("'", "''")
    py_code = (
        "from pathlib import Path; "
        f"Path(r'''{escaped_path}''').write_text(r'''{escaped_content}''', "
        "encoding='utf-8')"
    )
    command = (
        "$py = (Get-Command python).Source; "
        f"$args = @('-c', '{py_code}'); "
        "Start-Process -FilePath $py -ArgumentList $args -Verb RunAs"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return {
            "ok": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "returncode": completed.returncode,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
