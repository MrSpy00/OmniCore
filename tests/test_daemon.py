"""Unit tests for EventReactorDaemon in core/daemon.py."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from core.daemon import EventReactorDaemon


class TestEventReactorDaemon:
    """Test EventReactorDaemon life cycle and monitoring."""

    def test_singleton(self):
        d1 = EventReactorDaemon.get_instance()
        d2 = EventReactorDaemon.get_instance()
        assert d1 is d2

    def test_directory_watcher_and_snapshot(self, tmp_path):
        daemon = EventReactorDaemon()
        test_file = tmp_path / "hello.txt"
        test_file.write_text("content", encoding="utf-8")

        daemon.add_directory_watcher("test_watch", tmp_path)
        status = daemon.get_status()

        assert status["watcher_count"] == 1
        assert status["watchers"][0]["name"] == "test_watch"
        assert "hello.txt" in daemon._watchers["test_watch"]["last_snapshot"]

    def test_metric_alert_addition(self):
        daemon = EventReactorDaemon()
        daemon.add_metric_alert("cpu", threshold=90.0)
        daemon.add_metric_alert("ram", threshold=85.0)

        status = daemon.get_status()
        assert status["alert_count"] >= 2
        metrics = {a["metric"]: a for a in status["alerts"]}
        assert "cpu" in metrics
        assert metrics["cpu"]["threshold"] == 90.0
        assert "ram" in metrics

    @pytest.mark.asyncio
    async def test_check_alerts_triggers(self):
        daemon = EventReactorDaemon()
        daemon.add_metric_alert("cpu", threshold=50.0)
        daemon.add_metric_alert("ram", threshold=50.0)

        with (
            patch("psutil.cpu_percent", return_value=85.0),
            patch("psutil.virtual_memory") as mock_vm,
        ):
            mock_vm.return_value = MagicMock(percent=92.0)
            await daemon._check_alerts()

            assert daemon._alerts["cpu"]["triggered"] is True
            assert daemon._alerts["ram"]["triggered"] is True

    @pytest.mark.asyncio
    async def test_check_watchers_detects_change(self, tmp_path):
        daemon = EventReactorDaemon()
        test_file = tmp_path / "initial.txt"
        test_file.write_text("initial", encoding="utf-8")

        daemon.add_directory_watcher("fs_test", tmp_path)
        initial_snap = daemon._watchers["fs_test"]["last_snapshot"]

        # Modify directory
        new_file = tmp_path / "created.txt"
        new_file.write_text("new", encoding="utf-8")

        await daemon._check_watchers()
        updated_snap = daemon._watchers["fs_test"]["last_snapshot"]
        assert updated_snap != initial_snap
        assert "created.txt" in updated_snap

    @pytest.mark.asyncio
    async def test_ensure_running_in_loop(self):
        daemon = EventReactorDaemon()
        daemon.ensure_running()
        assert daemon._running is True
        assert daemon._loop_task is not None
        daemon._running = False
        daemon._loop_task.cancel()
        try:
            await daemon._loop_task
        except asyncio.CancelledError:
            pass
