from __future__ import annotations

from pathlib import Path

from tools.registry import discover_tool_classes


def test_dynamic_tool_discovery_loads_expected_optional_modules():
    classes = discover_tool_classes(Path("tools"))
    names = {cls.name for cls in classes}

    assert "desktop_send_notification" in names
    assert "gui_extract_text_from_region" in names
    assert "dev_glob_search" in names
    assert "dev_grep_analyzer" in names
    assert "sys_mcp_bridge" in names
    assert "agent_spawn_subtask" in names
