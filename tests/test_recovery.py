"""Unit tests for RecoveryEngine in core/recovery.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.recovery import RecoveryEngine
from models.tasks import TaskStep
from tools.base import BaseTool, ToolOutput, ToolStatus


class DummyTool(BaseTool):
    """Test tool stub for recovery testing."""

    name: str = "dummy_tool"
    description: str = "Dummy tool for testing"

    async def execute(self, tool_input: dict) -> ToolOutput:
        return ToolOutput(tool_name=self.name, status=ToolStatus.SUCCESS, result="ok")


@pytest.mark.asyncio
async def test_recovery_success_first_attempt():
    tool = DummyTool()
    engine = RecoveryEngine(max_retry_cap=2, timeout_seconds=5.0)
    step = TaskStep(id="s1", tool_name="dummy_tool", description="test step", max_retries=2)

    output = await engine.execute_with_retry(tool, {}, step)
    assert output.status == ToolStatus.SUCCESS
    assert output.result == "ok"
    assert step.retry_count == 0


@pytest.mark.asyncio
async def test_recovery_success_on_retry():
    tool = DummyTool()
    engine = RecoveryEngine(max_retry_cap=2, timeout_seconds=5.0)
    step = TaskStep(id="s1", tool_name="dummy_tool", description="test step", max_retries=2)

    mock_execute = AsyncMock(
        side_effect=[
            ToolOutput(tool_name=tool.name, status=ToolStatus.FAILURE, error="temporary glitch"),
            ToolOutput(tool_name=tool.name, status=ToolStatus.SUCCESS, result="recovered"),
        ]
    )
    tool.execute = mock_execute

    output = await engine.execute_with_retry(tool, {}, step)
    assert output.status == ToolStatus.SUCCESS
    assert output.result == "recovered"
    assert step.retry_count == 1


@pytest.mark.asyncio
async def test_recovery_loop_breaker_on_failure_exhaustion():
    tool = DummyTool()
    engine = RecoveryEngine(max_retry_cap=1, timeout_seconds=5.0)
    step = TaskStep(id="s1", tool_name="dummy_tool", description="test step", max_retries=1)

    mock_execute = AsyncMock(
        return_value=ToolOutput(tool_name=tool.name, status=ToolStatus.FAILURE, error="persistent err")
    )
    tool.execute = mock_execute

    output = await engine.execute_with_retry(tool, {}, step)
    assert output.status == ToolStatus.FAILURE
    assert "[LOOP_PROTECTION]" in (output.error or "")
    assert step.retry_count == 2


@pytest.mark.asyncio
async def test_recovery_timeout_handling_and_loop_breaker():
    tool = DummyTool()
    engine = RecoveryEngine(max_retry_cap=1, timeout_seconds=0.05)
    step = TaskStep(id="s1", tool_name="dummy_tool", description="test step", max_retries=1)

    async def slow_exec(inp: dict) -> ToolOutput:
        await asyncio.sleep(1.0)
        return ToolOutput(tool_name=tool.name, status=ToolStatus.SUCCESS)

    tool.execute = slow_exec

    output = await engine.execute_with_retry(tool, {}, step)
    assert output.status == ToolStatus.FAILURE
    assert "[LOOP_PROTECTION]" in (output.error or "")
    assert "timed out" in (output.error or "").lower()


@pytest.mark.asyncio
async def test_recovery_unhandled_exception_handling():
    tool = DummyTool()
    engine = RecoveryEngine(max_retry_cap=1, timeout_seconds=5.0)
    step = TaskStep(id="s1", tool_name="dummy_tool", description="test step", max_retries=1)

    tool.execute = AsyncMock(side_effect=RuntimeError("unexpected crash"))

    output = await engine.execute_with_retry(tool, {}, step)
    assert output.status == ToolStatus.FAILURE
    assert "[LOOP_PROTECTION]" in (output.error or "")
    assert "RuntimeError" in (output.error or "")
