"""Swarm Toolkit — Interact with multi-agent subagent swarm federation."""

from __future__ import annotations

from core.swarm import AgentSwarmManager
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class SwarmSpawnAgent(BaseTool):
    """Spawn a background subagent worker task for parallel execution."""

    name = "swarm_spawn_agent"
    description = (
        "Spawn a specialized background subagent worker for parallel task execution. "
        "Parameters: role (subagent title, e.g. Researcher), prompt (task instructions)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        role = str(self._first_param(params, "role", "type", default="Worker") or "").strip()
        prompt = str(self._first_param(params, "prompt", "instructions", default="") or "").strip()

        if not prompt:
            return self._failure("prompt parameter is required.")

        manager = AgentSwarmManager.get_instance()
        task_id = manager.spawn_subagent(role, prompt)

        return self._success(
            f"Subagent '{role}' spawned successfully with task ID '{task_id}'.",
            data={"task_id": task_id, "role": role},
        )


class SwarmListAgents(BaseTool):
    """List all active and completed subagent workers in the swarm."""

    name = "swarm_list_agents"
    description = "List all active and completed subagent workers in the swarm."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        manager = AgentSwarmManager.get_instance()
        agents = manager.list_subagents()
        return self._success(
            f"Found {len(agents)} subagent tasks in swarm.",
            data={"agents": agents, "count": len(agents)},
        )


class SwarmCollectResults(BaseTool):
    """Collect the execution results from a specific subagent task ID."""

    name = "swarm_collect_results"
    description = (
        "Collect execution results from a subagent task. "
        "Parameters: task_id (subagent task ID returned by swarm_spawn_agent)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        task_id = str(self._first_param(params, "task_id", "id", default="") or "").strip()

        if not task_id:
            return self._failure("task_id parameter is required.")

        manager = AgentSwarmManager.get_instance()
        result = manager.get_subagent_result(task_id)
        if not result:
            return self._failure(f"Subagent task '{task_id}' not found.")

        return self._success(
            f"Subagent '{task_id}' status: {result['status']}.",
            data=result,
        )
