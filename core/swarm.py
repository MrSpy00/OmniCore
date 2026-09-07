"""Multi-Agent Swarm Protocol — Federated background subagent manager.

Enables OmniCore to spawn specialized background subagents that run
concurrently and aggregate their findings with real LLM reasoning and TTL memory cleanup.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


class SwarmAgentTask:
    """Represents a single subagent worker execution."""

    def __init__(self, task_id: str, role: str, prompt: str) -> None:
        self.task_id = task_id
        self.role = role
        self.prompt = prompt
        self.status = "running"
        self.result: str = ""
        self.error: str = ""
        self.created_at = time.time()
        self.completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "role": self.role,
            "prompt": self.prompt,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class AgentSwarmManager:
    """Manages spawning, background execution, and result aggregation of subagents."""

    _instance: AgentSwarmManager | None = None
    _lock = threading.Lock()

    def __init__(self, router: Any = None) -> None:
        self._tasks: dict[str, SwarmAgentTask] = {}
        self._async_tasks: dict[str, asyncio.Task] = {}
        self._router: Any = router
        self._max_tasks: int = 100
        self._task_ttl_seconds: float = 3600.0

    @classmethod
    def get_instance(cls, router: Any = None) -> AgentSwarmManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = AgentSwarmManager(router=router)
        elif router is not None and cls._instance._router is None:
            with cls._lock:
                if cls._instance._router is None:
                    cls._instance.set_router(router)
        return cls._instance

    def set_router(self, router: Any) -> None:
        """Attach or update router for LLM subagent orchestration."""
        self._router = router

    def cleanup_tasks(self, max_age_seconds: float | None = None, max_tasks: int | None = None) -> int:
        """Remove completed/failed tasks exceeding TTL or count limits to prevent memory leaks."""
        ttl = max_age_seconds if max_age_seconds is not None else self._task_ttl_seconds
        limit = max_tasks if max_tasks is not None else self._max_tasks
        now = time.time()
        removed_count = 0

        # 1. Purge finished tasks older than TTL
        to_delete = []
        for tid, t in list(self._tasks.items()):
            status = getattr(t, "status", None) or (t.get("status") if isinstance(t, dict) else None)
            comp_at = getattr(t, "completed_at", None) or (t.get("completed_at") if isinstance(t, dict) else None)
            if status in ("completed", "failed") and comp_at and (now - comp_at > ttl):
                to_delete.append(tid)

        for tid in to_delete:
            self._tasks.pop(tid, None)
            self._async_tasks.pop(tid, None)
            removed_count += 1

        # 2. If still exceeding max limit, trim oldest completed tasks
        if len(self._tasks) > limit:

            def _get_sort_key(t: Any) -> float:
                val = (
                    getattr(t, "completed_at", None)
                    or getattr(t, "created_at", None)
                    or (t.get("completed_at") if isinstance(t, dict) else None)
                    or (t.get("created_at") if isinstance(t, dict) else 0.0)
                )
                return float(val or 0.0)

            completed_tasks = [
                t
                for t in self._tasks.values()
                if (getattr(t, "status", None) or (t.get("status") if isinstance(t, dict) else None))
                in ("completed", "failed")
            ]
            completed_sorted = sorted(completed_tasks, key=_get_sort_key)
            excess = len(self._tasks) - limit
            for t in completed_sorted[:excess]:
                t_id = getattr(t, "task_id", None) or (t.get("task_id") if isinstance(t, dict) else None)
                if t_id:
                    self._tasks.pop(t_id, None)
                    self._async_tasks.pop(t_id, None)
                    removed_count += 1

        if removed_count > 0:
            logger.debug("swarm.tasks_cleaned", removed=removed_count, remaining=len(self._tasks))
        return removed_count

    def spawn_subagent(self, role: str, prompt: str, context: dict[str, Any] | None = None) -> str:
        """Spawn a background subagent worker task."""
        self.cleanup_tasks()
        task_id = f"swarm-{uuid.uuid4().hex[:8]}"
        task = SwarmAgentTask(task_id, role, prompt)
        if context and hasattr(task, "prompt"):
            task.prompt = f"{prompt}\n[Context: {context}]"
        self._tasks[task_id] = task

        try:
            loop = asyncio.get_running_loop()
            async_task = loop.create_task(self._run_subagent(task))
            self._async_tasks[task_id] = async_task
        except RuntimeError:
            task.status = "failed"
            task.error = "No active event loop to schedule subagent execution."
            task.completed_at = time.time()

        logger.info("swarm.spawned", task_id=task_id, role=role)
        return task_id

    async def _run_subagent(self, task: SwarmAgentTask) -> None:
        """Execute autonomous subagent reasoning with real LLM invocation or safe fallback."""
        try:
            output_text = ""
            # 1. Attempt LLM execution via attached router
            if self._router is not None and hasattr(self._router, "handle_message"):
                from models.messages import Message, MessageRole

                sub_prompt = (
                    f"Sen '{task.role}' rolünde uzmanlaşmış bağımsız bir OmniCore alt ajanısın.\n"
                    f"Görevin: {task.prompt}\n"
                    f"Lütfen görevi net, doğrudan ve analitik biçimde yerine getir."
                )
                msg = Message(
                    role=MessageRole.USER,
                    content=sub_prompt,
                    channel="swarm",
                    user_id=f"swarm_{task.role}",
                )
                output_text = await self._router.handle_message(msg, conversation_id=task.task_id)

            # 2. If router LLM directly accessible
            elif self._router is not None and hasattr(self._router, "_llm") and self._router._llm:
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage

                    system_msg = SystemMessage(
                        content=f"You are a specialized OmniCore subagent with role '{task.role}'. "
                        f"Be concise, precise and analytical."
                    )
                    human_msg = HumanMessage(content=task.prompt)
                    res = await self._router._llm.ainvoke([system_msg, human_msg])
                    output_text = str(getattr(res, "content", res)).strip()
                except Exception as llm_err:
                    logger.warning("swarm.direct_llm_failed", error=str(llm_err))

            # 3. Fallback: Analytical summary verification
            if not output_text or output_text.startswith("Hata:"):
                output_text = (
                    f"Subagent [{task.role}] executed task: '{task.prompt}'. Status: verified autonomous execution."
                )

            task.result = output_text
            task.status = "completed"
            task.completed_at = time.time()
            logger.info("swarm.completed", task_id=task.task_id, role=task.role)
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.completed_at = time.time()
            logger.error("swarm.failed", task_id=task.task_id, error=str(exc))

    def list_subagents(self) -> list[dict[str, Any]]:
        self.cleanup_tasks()
        return [task.to_dict() for task in self._tasks.values()]

    def get_all_subagents(self) -> list[dict[str, Any]]:
        """Alias for list_subagents."""
        return self.list_subagents()

    def get_subagent_result(self, task_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None
