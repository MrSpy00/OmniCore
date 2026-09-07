"""Unit tests for GPU VRAM Monitor and Game Process Detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.vram_monitor import VRAMMonitor, detect_running_games, get_vram_monitor


class TestGameDetection:
    """Test game and game-engine process detection."""

    def test_detect_running_games_found(self):
        mock_proc1 = MagicMock()
        mock_proc1.info = {"name": "cs2.exe"}
        mock_proc2 = MagicMock()
        mock_proc2.info = {"name": "chrome.exe"}
        mock_proc3 = MagicMock()
        mock_proc3.info = {"name": "ue5editor.exe"}

        with patch("psutil.process_iter", return_value=[mock_proc1, mock_proc2, mock_proc3]):
            games = detect_running_games()
            assert "cs2.exe" in games
            assert "ue5editor.exe" in games
            assert "chrome.exe" not in games

    def test_detect_running_games_none(self):
        mock_proc = MagicMock()
        mock_proc.info = {"name": "python.exe"}

        with patch("psutil.process_iter", return_value=[mock_proc]):
            games = detect_running_games()
            assert games == []

    def test_detect_running_games_exception_handled(self):
        with patch("psutil.process_iter", side_effect=RuntimeError("psutil access error")):
            games = detect_running_games()
            assert games == []


class TestVRAMMonitorLifecycle:
    """Test VRAMMonitor initialization, query, and monitoring thresholds."""

    def test_init_and_status(self):
        monitor = VRAMMonitor(poll_interval=1.0, threshold_high=0.80, threshold_critical=0.90)
        assert monitor._poll_interval == 1.0
        assert monitor._threshold_high == 0.80
        assert monitor._threshold_critical == 0.90
        assert monitor._running is False

    def test_query_gpu_nvidia_smi_success(self):
        monitor = VRAMMonitor()
        mock_stdout = "NVIDIA GeForce RTX 3070, 4000, 8000, 65, 50\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_stdout)
            status = monitor._query_gpu()
            assert status["available"] is True
            assert status["gpu_name"] == "NVIDIA GeForce RTX 3070"
            assert status["vram_used_mb"] == 4000.0
            assert status["vram_total_mb"] == 8000.0
            assert status["vram_used_pct"] == 0.5
            assert status["temperature"] == 65.0
            assert status["gpu_utilization"] == 50.0

    def test_query_gpu_nvidia_smi_unavailable(self):
        monitor = VRAMMonitor()

        with patch("subprocess.run", side_effect=FileNotFoundError("nvidia-smi not found")):
            status = monitor._query_gpu()
            assert status["available"] is False

    def test_start_and_stop(self):
        monitor = VRAMMonitor(poll_interval=0.1)
        with patch.object(monitor, "_poll_loop", return_value=None):
            assert monitor.start() is True
            assert monitor._running is True
            assert monitor.start() is True
            monitor.stop()
            assert monitor._running is False

    def test_unload_ollama_models_success(self):
        monitor = VRAMMonitor()
        with patch("httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            assert monitor._unload_ollama_models() is True

    def test_unload_ollama_models_failure(self):
        monitor = VRAMMonitor()
        with patch("httpx.post", side_effect=RuntimeError("connection error")):
            assert monitor._unload_ollama_models() is False

    def test_get_vram_monitor_singleton(self):
        m1 = get_vram_monitor()
        m2 = get_vram_monitor()
        assert m1 is m2

    def test_poll_loop_single_iteration(self):
        monitor = VRAMMonitor(poll_interval=0.001)
        monitor._running = True
        called = False

        def cb(status):
            nonlocal called
            called = True
            monitor._running = False  # Break loop

        monitor._callbacks.append(cb)
        with (
            patch("core.vram_monitor.detect_running_games", return_value=["cs2.exe"]),
            patch.object(monitor, "_query_gpu", return_value={"available": True, "vram_used_pct": 0.98}),
            patch.object(monitor, "_unload_ollama_models", return_value=True),
            patch("time.sleep", return_value=None),
        ):
            monitor._poll_loop()

        assert called is True
        assert monitor._last_status["vram_used_pct"] == 0.98
        assert "cs2.exe" in monitor._last_status["active_games"]
