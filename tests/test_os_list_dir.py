from __future__ import annotations

import pytest

import tools.base as base_mod
from models.tools import ToolInput, ToolStatus
from tools.os_toolkit import OsListDir


@pytest.mark.asyncio
async def test_list_dir_resolves_placeholder_username(monkeypatch, tmp_path):
    home = tmp_path / "mrSpy"
    desktop = home / "Desktop"
    desktop.mkdir(parents=True)
    (desktop / "note.txt").write_text("hello", encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(
        base_mod,
        "_windows_special_folders",
        lambda: {
            "desktop": desktop.resolve(),
            "documents": (home / "Documents").resolve(),
            "downloads": (home / "Downloads").resolve(),
        },
    )

    tool = OsListDir()
    result = await tool.execute(
        ToolInput(tool_name="os_list_dir", parameters={"path": r"C:\Users\<Username>\Desktop"})
    )

    assert result.status == ToolStatus.SUCCESS
    assert result.data["path"] == str(desktop.resolve())
    assert any(entry["name"] == "note.txt" for entry in result.data["entries"])
