"""Continuous Background Daemon — Async Event Reactor.

Monitors directories, system metrics, and scheduled triggers in the background
without blocking gateway user interaction.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import psutil

from config.logging import get_logger

logger = get_logger(__name__)


class EventReactorDaemon:
    """Asynchronous background event reactor daemon."""

    _instance: EventReactorDaemon | None = None

    def __init__(self) -> None:
        self._watchers: dict[str, dict[str, Any]] = {}
        self._alerts: dict[str, dict[str, Any]] = {}
        self._running = False
        self._loop_task: asyncio.Task | None = None

    @classmethod
    def get_instance(cls) -> EventReactorDaemon:
        if cls._instance is None:
            cls._instance = EventReactorDaemon()
        return cls._instance

    def add_directory_watcher(self, name: str, path: Path) -> None:
        self._watchers[name] = {
            "path": path,
            "last_snapshot": self._snapshot_dir(path),
            "added_at": time.time(),
        }
        logger.info("daemon.watcher_added", name=name, path=str(path))
        self.ensure_running()

    def add_metric_alert(self, metric: str, threshold: float) -> None:
        self._alerts[metric] = {
            "threshold": threshold,
            "triggered": False,
            "added_at": time.time(),
        }
        logger.info("daemon.alert_added", metric=metric, threshold=threshold)
        self.ensure_running()

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "watcher_count": len(self._watchers),
            "alert_count": len(self._alerts),
            "watchers": [{"name": k, "path": str(v["path"])} for k, v in self._watchers.items()],
            "alerts": [
                {"metric": k, "threshold": v["threshold"], "triggered": v["triggered"]} for k, v in self._alerts.items()
            ],
        }

    def ensure_running(self) -> None:
        if not self._running:
            self._running = True
            try:
                loop = asyncio.get_running_loop()
                self._loop_task = loop.create_task(self._main_loop())
            except RuntimeError:
                pass

    async def _main_loop(self) -> None:
        logger.info("daemon.started")
        while self._running:
            try:
                await self._check_watchers()
                await self._check_alerts()
            except Exception as exc:
                logger.error("daemon.loop_error", error=str(exc))
            await asyncio.sleep(5)

    async def _check_watchers(self) -> None:
        for name, watcher in list(self._watchers.items()):
            path: Path = watcher["path"]
            if not path.exists():
                continue
            current = await asyncio.to_thread(self._snapshot_dir, path)
            old = watcher["last_snapshot"]
            if current != old:
                logger.info("daemon.directory_changed", name=name, path=str(path))
                watcher["last_snapshot"] = current

    async def _check_alerts(self) -> None:
        if "cpu" in self._alerts:
            cpu = psutil.cpu_percent(interval=None)
            if cpu > self._alerts["cpu"]["threshold"]:
                logger.warning("daemon.cpu_alert_triggered", value=cpu)
                self._alerts["cpu"]["triggered"] = True

        if "ram" in self._alerts:
            ram = psutil.virtual_memory().percent
            if ram > self._alerts["ram"]["threshold"]:
                logger.warning("daemon.ram_alert_triggered", value=ram)
                self._alerts["ram"]["triggered"] = True

    @staticmethod
    def _snapshot_dir(path: Path) -> dict[str, float]:
        snapshot: dict[str, float] = {}
        try:
            for item in path.glob("*"):
                if item.is_file():
                    snapshot[item.name] = item.stat().st_mtime
        except Exception:
            pass
        return snapshot
