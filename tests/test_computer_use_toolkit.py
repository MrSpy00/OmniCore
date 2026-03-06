from __future__ import annotations

from pathlib import Path

import pytest

from models.tools import ToolInput, ToolStatus
from tools.computer_use_toolkit import GuiExtractTextFromRegion


@pytest.mark.asyncio
async def test_region_extraction_uses_gemini_analysis(monkeypatch, tmp_workspace):
    from config.settings import get_settings

    monkeypatch.setenv("SANDBOX_ROOT", str(tmp_workspace))
    get_settings.cache_clear()

    captured = {}

    def fake_capture_region(path, region):
        Path(path).write_bytes(b"fake-image")
        captured["region"] = region

    def fake_analyze(path, prompt):
        captured["path"] = Path(path)
        captured["prompt"] = prompt
        return "visible text"

    monkeypatch.setattr("tools.computer_use_toolkit._capture_region", fake_capture_region)
    monkeypatch.setattr("tools.computer_use_toolkit.analyze_image_with_gemini", fake_analyze)

    tool = GuiExtractTextFromRegion()
    result = await tool.execute(
        ToolInput(
            tool_name="gui_extract_text_from_region",
            parameters={"left": 1, "top": 2, "width": 30, "height": 40, "output_path": "r.png"},
        )
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.data["text"] == "visible text"
    assert captured["region"] == {"left": 1, "top": 2, "width": 30, "height": 40}
    assert captured["path"].name == "r.png"
    assert "Read all visible text in this screenshot region exactly" in captured["prompt"]


def test_capture_region_rejects_zero_sized_region(tmp_path):
    from tools.computer_use_toolkit import _capture_region

    with pytest.raises(ValueError, match="width and height must be greater than zero"):
        _capture_region(tmp_path / "region.png", {"left": 0, "top": 0, "width": 0, "height": 10})
