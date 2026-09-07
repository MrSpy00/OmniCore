"""Unit test suite for AgentSwarmManager and multi-agent coordination."""

from __future__ import annotations

import asyncio
import time

import pytest

from core.swarm import AgentSwarmManager, SwarmAgentTask


@pytest.mark.asyncio
async def test_agent_swarm_manager_lifecycle():
    manager = AgentSwarmManager.get_instance()
    assert manager is not None

    # Spawn subagent
    task_id = manager.spawn_subagent(
        role="DataProcessor",
        prompt="Process user log data",
        context={"batch_size": 50},
    )
    assert task_id.startswith("swarm-")

    # Get status immediately
    status = manager.get_subagent_result(task_id)
    assert status is not None
    assert status["role"] == "DataProcessor"
    assert "Process user log data" in status["prompt"]
    assert status["status"] in ("running", "completed", "failed")

    # List all subagents
    all_agents = manager.get_all_subagents()
    assert any(a["task_id"] == task_id for a in all_agents)


@pytest.mark.asyncio
async def test_agent_swarm_manager_cleanup():
    manager = AgentSwarmManager.get_instance()

    # Create dummy tasks with simulated old timestamps using SwarmAgentTask
    old_task_id = "swarm-test-old-task"
    old_task = SwarmAgentTask(old_task_id, "OldRole", "Old prompt")
    old_task.status = "completed"
    old_task.created_at = time.time() - 7200
    old_task.completed_at = time.time() - 7100
    manager._tasks[old_task_id] = old_task

    # Run cleanup with 3600 max age
    cleaned = manager.cleanup_tasks(max_age_seconds=3600, max_tasks=100)
    assert cleaned >= 1
    assert old_task_id not in manager._tasks


@pytest.mark.asyncio
async def test_agent_swarm_manager_fallback_execution():
    manager = AgentSwarmManager.get_instance()

    # Subagent with mock execution
    task_id = manager.spawn_subagent(
        role="Summarizer",
        prompt="Summarize system metrics",
    )

    # Wait for completion (simulated fallback finishes quickly)
    res = None
    for _ in range(30):
        res = manager.get_subagent_result(task_id)
        if res and res["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    assert res is not None
    assert "role" in res


@pytest.mark.asyncio
async def test_agent_swarm_manager_cleanup_excess_limit():
    manager = AgentSwarmManager.get_instance()

    # Create 5 completed tasks
    for i in range(5):
        tid = f"swarm-test-limit-{i}"
        task = SwarmAgentTask(tid, f"Role{i}", f"Prompt{i}")
        task.status = "completed"
        task.completed_at = time.time() - i
        manager._tasks[tid] = task

    # Cleanup with max_tasks=2
    cleaned = manager.cleanup_tasks(max_age_seconds=99999, max_tasks=2)
    assert cleaned >= 3


@pytest.mark.asyncio
async def test_agent_swarm_manager_with_attached_router():
    from unittest.mock import AsyncMock, MagicMock

    manager = AgentSwarmManager.get_instance()
    mock_router = MagicMock()
    mock_router.handle_message = AsyncMock(return_value="Router processed task result")
    manager.set_router(mock_router)

    task_id = manager.spawn_subagent(role="CodeReviewer", prompt="Review diff")

    # Wait for completion
    res = None
    for _ in range(30):
        res = manager.get_subagent_result(task_id)
        if res and res["status"] in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    assert res is not None
    assert res["status"] == "completed"
    assert "Router processed" in (res.get("result") or "")
    manager.set_router(None)
