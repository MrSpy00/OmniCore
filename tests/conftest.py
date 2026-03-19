"""Shared pytest fixtures for OmniCore tests."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.settings import Settings
from memory.short_term import ShortTermMemory
from memory.state import StateTracker
from models.messages import Message, MessageRole
from models.tools import ToolInput
from tools.registry import ToolRegistry
from tools.os_toolkit import OsReadFile, OsWriteFile, OsListDir
from tools.api_toolkit import ApiDatetime


# ---------------------------------------------------------------------------
# Settings override — use temp dirs so tests don't touch real state.
# ---------------------------------------------------------------------------
@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture()
def settings(tmp_path: Path, tmp_workspace: Path, monkeypatch) -> Settings:
    """Create a Settings instance pointing at temporary directories."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("USERPROFILE", str(tmp_workspace))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")

    # Clear the cached settings so it picks up the monkeypatched env.
    from config.settings import get_settings

    get_settings.cache_clear()

    s = Settings(
        google_api_key="test-key-not-real",
        chroma_persist_dir=tmp_path / "chroma",
        sqlite_db_path=tmp_path / "test.db",
        scheduler_enabled=False,
    )
    return s


# ---------------------------------------------------------------------------
# Memory fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def short_term() -> ShortTermMemory:
    return ShortTermMemory(max_messages=10)


@pytest.fixture()
async def state_tracker(tmp_path: Path):
    db_path = tmp_path / "state.db"
    tracker = StateTracker(db_path)
    await tracker.initialize()
    yield tracker  # type: ignore[misc]
    await tracker.close()


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------
@pytest.fixture()
def tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(OsReadFile())
    registry.register(OsWriteFile())
    registry.register(OsListDir())
    registry.register(ApiDatetime())
    return registry


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------
@pytest.fixture()
def user_message() -> Message:
    return Message(
        role=MessageRole.USER,
        content="Hello, OmniCore!",
        channel="test",
        user_id="test_user",
    )


@pytest.fixture()
def sample_tool_input() -> ToolInput:
    return ToolInput(
        tool_name="os_read_file",
        parameters={"path": "test.txt"},
    )
