"""Unit and integration tests for OmniCore's next-generation architectural enhancements."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.planner import WorkflowExecutionEngine
from interfaces.dashboard import create_dashboard_app
from interfaces.spotlight import SpotlightBar
from interfaces.tray_companion import SystemTrayCompanion, _create_tray_icon
from interfaces.voice_duplex import DuplexVoiceEngine, _calculate_rms
from models.tools import ToolInput, ToolStatus
from tools.smart_clipboard_toolkit import (
    SmartClipboardAnalyzeTraceback,
    SmartClipboardInspect,
    _detect_content_type,
)
from tools.vision_toolkit import VisionInstantScreenContext, VisionSetOfMarkAnnotate
from tools.windows_uia_toolkit import (
    WindowsClickUIElement,
    WindowsInspectUIElements,
    WindowsSetControlText,
)


# ==========================================
# 1. Windows UIA Toolkit Tests
# ==========================================
@pytest.mark.asyncio
async def test_windows_uia_inspect_elements():
    tool = WindowsInspectUIElements()
    mock_res = {
        "success": True,
        "window": {"hwnd": 12345, "title": "Test App", "rect": (0, 0, 800, 600)},
        "element_count": 2,
        "elements": [
            {"hwnd": 11, "text": "OK", "class": "Button", "center": {"x": 100, "y": 200}},
            {"hwnd": 12, "text": "Cancel", "class": "Button", "center": {"x": 200, "y": 200}},
        ],
    }

    with patch("tools.windows_uia_toolkit.asyncio.to_thread", AsyncMock(return_value=mock_res)):
        inp = ToolInput(tool_name="windows_inspect_ui_elements", parameters={"window_title": "Test App"})
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "Test App" in out.result
        assert "2 etkileşimli" in out.result


@pytest.mark.asyncio
async def test_windows_uia_click_element():
    tool = WindowsClickUIElement()
    mock_res = {
        "success": True,
        "clicked_element": "OK",
        "coordinates": (100, 200),
        "window": "Test App",
    }

    with patch("tools.windows_uia_toolkit.asyncio.to_thread", AsyncMock(return_value=mock_res)):
        inp = ToolInput(tool_name="windows_click_ui_element", parameters={"element_name": "OK"})
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "OK" in out.result


@pytest.mark.asyncio
async def test_windows_uia_set_control_text():
    tool = WindowsSetControlText()
    mock_res = {
        "success": True,
        "window": "Test App",
        "text_length": 11,
    }

    with patch("tools.windows_uia_toolkit.asyncio.to_thread", AsyncMock(return_value=mock_res)):
        inp = ToolInput(tool_name="windows_set_control_text", parameters={"text": "Hello World"})
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "11 karakterlik" in out.result


# ==========================================
# 2. Vision Tools Tests
# ==========================================
@pytest.mark.asyncio
async def test_vision_instant_screen_context():
    tool = VisionInstantScreenContext()
    mock_res = {
        "screenshot_path": "test.png",
        "analysis": "Ekran üzerinde açık bir Python traceback hatası görünüyor.",
        "window": "Active Desktop",
    }

    with patch("tools.vision_toolkit.asyncio.to_thread", AsyncMock(return_value=mock_res)):
        inp = ToolInput(tool_name="vision_instant_screen_context", parameters={"prompt": "Ne var?"})
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "traceback" in out.result


@pytest.mark.asyncio
async def test_vision_set_of_mark_annotate():
    tool = VisionSetOfMarkAnnotate()
    mock_res = {
        "output_path": "som.png",
        "marks_count": 12,
        "grid": {"rows": 5, "cols": 9},
        "marks": [{"id": 1, "box": [0, 0, 100, 100], "center": (50, 50)}],
    }

    with patch("tools.vision_toolkit.asyncio.to_thread", AsyncMock(return_value=mock_res)):
        inp = ToolInput(tool_name="vision_som_annotate", parameters={})
        out = await tool.execute(inp)
        assert out.status == ToolStatus.SUCCESS
        assert "12" in out.result
        assert "5×9" in out.result


# ==========================================
# 3. Voice Duplex Barge-in & RMS Tests
# ==========================================
def test_voice_calculate_rms():
    # Silent bytes
    silence = b"\x00\x00" * 100
    assert _calculate_rms(silence) == 0.0

    # High amplitude square wave
    loud = (b"\x7f\x7f" + b"\x80\x80") * 50
    assert _calculate_rms(loud) > 0.0


@pytest.mark.asyncio
async def test_voice_duplex_bargein_interruption():
    engine = DuplexVoiceEngine(energy_threshold=500.0)
    await engine.start_session()

    # Queue speech chunk
    await engine.queue_speech_output(b"\x01\x00" * 100)
    assert engine.is_speaking is True
    assert not engine.output_audio_queue.empty()

    # Trigger interruption
    interrupted = engine.interrupt_playback()
    assert interrupted is True
    assert engine.is_speaking is False
    assert engine.output_audio_queue.empty()
    assert engine._interrupted_count == 1

    await engine.stop_session()


# ==========================================
# 4. Spotlight & Tray Companion Tests
# ==========================================
@pytest.mark.asyncio
async def test_spotlight_bar():
    mock_router = MagicMock()
    mock_router.handle_message = AsyncMock(return_value="YouTube açıldı.")
    spotlight = SpotlightBar(mock_router)

    res = await spotlight.execute_query("elraenn aç")
    assert res["status"] == "success"
    assert res["reply"] == "YouTube açıldı."


def test_system_tray_companion_icon_and_tooltip():
    mock_router = MagicMock()
    mock_router._runtime_provider = "gemini"
    tray = SystemTrayCompanion(mock_router)

    icon = _create_tray_icon(32)
    assert icon.size == (32, 32)

    tooltip = tray.get_telemetry_tooltip()
    assert "OmniCore" in tooltip
    assert "gemini" in tooltip


# ==========================================
# 5. Checkpointed Workflow Engine Tests
# ==========================================
def test_workflow_execution_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "wf_test.db"
        engine = WorkflowExecutionEngine(db_file)

        # Commit step
        engine.checkpoint_step("test_wf", 0, "os_read_file", "success", {"path": "main.py"}, {"size": 120})
        steps = engine.get_completed_steps("test_wf")
        assert 0 in steps
        assert steps[0]["tool"] == "os_read_file"
        assert steps[0]["status"] == "success"

        # Alternative branching logic
        alt_tool, alt_params = engine.suggest_alternative_branch("os_read_file", "file not found: main.py")
        assert alt_tool == "es_fast_search"


# ==========================================
# 6. Dashboard 2.0 Endpoints Tests
# ==========================================
@pytest.mark.asyncio
async def test_dashboard_2_endpoints():
    app = create_dashboard_app()
    client = TestClient(app)

    # Graph data route
    r_graph = client.get("/api/graph/data")
    assert r_graph.status_code == 200
    assert "nodes" in r_graph.json()
    assert "edges" in r_graph.json()

    # Processes route
    r_proc = client.get("/api/system/processes")
    assert r_proc.status_code == 200
    assert isinstance(r_proc.json(), list)


# ==========================================
# 7. Smart Clipboard Toolkit Tests
# ==========================================
def test_smart_clipboard_content_detection():
    # Traceback detection
    tb_text = """Traceback (most recent call last):
  File "main.py", line 42, in <module>
ZeroDivisionError: division by zero"""
    det = _detect_content_type(tb_text)
    assert det["category"] == "error"
    assert det["type"] == "python_traceback"

    # JSON detection
    json_text = '{"name": "OmniCore", "version": "0.1.0"}'
    det_json = _detect_content_type(json_text)
    assert det_json["category"] == "data"
    assert det_json["type"] == "json"

    # SQL detection
    sql_text = "SELECT * FROM users WHERE active = 1;"
    det_sql = _detect_content_type(sql_text)
    assert det_sql["category"] == "database"


@pytest.mark.asyncio
async def test_smart_clipboard_tools():
    tool_inspect = SmartClipboardInspect()
    tool_analyze = SmartClipboardAnalyzeTraceback()

    tb_sample = """Traceback (most recent call last):
  File "app.py", line 15, in run
ValueError: Invalid configuration"""

    with patch("tools.smart_clipboard_toolkit.pyperclip.paste", return_value=tb_sample):
        out_insp = await tool_inspect.execute(ToolInput(tool_name="smart_clipboard_inspect", parameters={}))
        assert out_insp.status == ToolStatus.SUCCESS
        assert "python_traceback" in out_insp.result

        out_ana = await tool_analyze.execute(ToolInput(tool_name="smart_clipboard_analyze_traceback", parameters={}))
        assert out_ana.status == ToolStatus.SUCCESS
        assert "ValueError" in out_ana.result
        assert "app.py" in out_ana.result


def test_router_hardware_adaptive_routing():
    from unittest.mock import MagicMock

    from core.router import CognitiveRouter

    router = MagicMock(spec=CognitiveRouter)
    router._runtime_provider = "ollama"
    router._provider_has_credentials = MagicMock(return_value=True)

    # Test battery routing: low battery on laptop -> switches away from local ollama
    mock_battery = MagicMock(percent=18, power_plugged=False)
    with patch("psutil.sensors_battery", return_value=mock_battery):
        route = CognitiveRouter._power_and_hardware_adaptive_route(router)
        assert route in ("groq", "gemini")

    # Test GPU VRAM protection: GPU VRAM > 85% -> switches away from local ollama
    mock_plugged = MagicMock(percent=90, power_plugged=True)
    mock_gpu = {"available": True, "vram_total_mb": "8192", "vram_used_mb": "7500"}
    with patch("psutil.sensors_battery", return_value=mock_plugged), \
         patch("tools.hardware_telemetry_toolkit._get_nvidia_gpu_info", return_value=mock_gpu):
        route = CognitiveRouter._power_and_hardware_adaptive_route(router)
        assert route in ("gemini", "groq")

