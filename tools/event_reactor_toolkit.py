"""Event Reactor Toolkit — Manage continuous background daemons and alerts."""

from __future__ import annotations

from pathlib import Path

from core.daemon import EventReactorDaemon
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class DaemonWatchDirectory(BaseTool):
    """Add a directory to the background event reactor for file change monitoring."""

    name = "daemon_watch_directory"
    description = (
        "Watch a directory in the background for new or modified files. "
        "Parameters: path (directory path to watch), name (label for watcher)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path_str = str(self._first_param(params, "path", "dir", default="") or "").strip()
        name = str(self._first_param(params, "name", default="dir_watcher") or "").strip()

        if not path_str:
            return self._failure("path parameter is required.")

        target = Path(path_str)
        if not target.exists() or not target.is_dir():
            return self._failure(f"Directory not found: {target}")

        daemon = EventReactorDaemon.get_instance()
        daemon.add_directory_watcher(name, target)

        return self._success(
            f"Background directory watcher '{name}' added for {target}.",
            data={"watcher": name, "path": str(target)},
        )


class DaemonAddAlert(BaseTool):
    """Add a system resource threshold alert (CPU/RAM)."""

    name = "daemon_add_alert"
    description = (
        "Add a background alert for CPU or RAM usage threshold. "
        "Parameters: metric (cpu|ram), threshold (percentage limit, e.g. 90)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        metric = str(self._first_param(params, "metric", default="cpu") or "").strip().lower()
        threshold = float(self._first_param(params, "threshold", "limit", default=90.0) or 90.0)

        if metric not in {"cpu", "ram"}:
            return self._failure("metric must be 'cpu' or 'ram'.")

        daemon = EventReactorDaemon.get_instance()
        daemon.add_metric_alert(metric, threshold)

        return self._success(
            f"Background alert for {metric.upper()} threshold > {threshold}% added.",
            data={"metric": metric, "threshold": threshold},
        )


class DaemonStatus(BaseTool):
    """Check the status of active background daemons, watchers, and alerts."""

    name = "daemon_status"
    description = "Check the status of active background daemons, watchers, and alerts."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        daemon = EventReactorDaemon.get_instance()
        status = daemon.get_status()
        return self._success("Background daemon status retrieved.", data=status)
