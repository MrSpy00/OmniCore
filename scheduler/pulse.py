"""Autonomous Pulse — APScheduler daemon for proactive tasks.

Runs in the background and fires scheduled jobs (morning briefing,
file cleanup, etc.) by feeding synthetic messages into the
CognitiveRouter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config.logging import get_logger
from config.settings import get_settings
from models.messages import Message, MessageRole

if TYPE_CHECKING:
    from core.router import CognitiveRouter
    from memory.state import StateTracker

logger = get_logger(__name__)


def _build_scheduler() -> AsyncIOScheduler:
    """Build an AsyncIOScheduler with SQLite persistence if SQLAlchemy is available."""
    settings = get_settings()
    try:
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # type: ignore[import]

        db_path = settings.scheduler_db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path.resolve()}"
        jobstores = {"default": SQLAlchemyJobStore(url=url)}
        scheduler = AsyncIOScheduler(jobstores=jobstores)
        logger.info("pulse.jobstore", backend="sqlite", path=str(db_path))
        return scheduler
    except ImportError:
        logger.warning(
            "pulse.jobstore_fallback",
            reason="SQLAlchemy not installed; using in-memory job store",
        )
        return AsyncIOScheduler()

class AutonomousPulse:
    """Background scheduler that executes proactive tasks.

    Parameters
    ----------
    router:
        The CognitiveRouter for processing scheduled tasks.
    state_tracker:
        For loading persisted job definitions.
    """

    def __init__(
        self,
        router: CognitiveRouter,
        state_tracker: StateTracker,
    ) -> None:
        self._router = router
        self._state = state_tracker
        self._scheduler = _build_scheduler()

    async def start(self) -> None:
        """Load jobs from the database and start the scheduler."""
        settings = get_settings()
        if not settings.scheduler_enabled:
            logger.info("pulse.disabled")
            return

        # Register built-in jobs.
        from scheduler.jobs import BUILTIN_JOBS

        for job_def in BUILTIN_JOBS:
            self._scheduler.add_job(
                self._execute_scheduled_task,
                trigger=CronTrigger.from_crontab(job_def["cron"]),
                id=job_def["id"],
                name=job_def["name"],
                kwargs={"prompt": job_def["prompt"]},
                replace_existing=True,
            )
            logger.info(
                "pulse.job_registered",
                job_id=job_def["id"],
                name=job_def["name"],
                cron=job_def["cron"],
            )

        # Load user-defined jobs from the database.
        persisted = await self._state.list_scheduled_jobs(enabled_only=True)
        for job in persisted:
            self._scheduler.add_job(
                self._execute_scheduled_task,
                trigger=CronTrigger.from_crontab(job["cron_expr"]),
                id=job["id"],
                name=job["job_name"],
                kwargs={"prompt": job.get("config", {}).get("prompt", job["job_name"])},
                replace_existing=True,
            )

        self._scheduler.start()
        logger.info("pulse.started", job_count=len(self._scheduler.get_jobs()))

    async def stop(self) -> None:
        """Shut down the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("pulse.stopped")

    async def _execute_scheduled_task(self, prompt: str) -> None:
        """Feed a synthetic user message into the router."""
        logger.info("pulse.executing", prompt=prompt[:100])
        msg = Message(
            role=MessageRole.USER,
            content=prompt,
            channel="scheduler",
            user_id="system",
        )
        try:
            reply = await self._router.handle_message(msg, conversation_id="scheduler")
            logger.info("pulse.completed", prompt=prompt[:60], reply=reply[:200])
            await self._state.log_audit(
                "scheduled_task_completed",
                f"Prompt: {prompt[:100]} | Reply: {reply[:200]}",
            )
        except Exception as exc:
            logger.error("pulse.failed", prompt=prompt[:60], error=str(exc))
            await self._state.log_audit(
                "scheduled_task_failed",
                f"Prompt: {prompt[:100]} | Error: {exc}",
            )

    def list_jobs(self) -> list[dict]:
        """Return a summary of all currently scheduled jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(next_run) if next_run else "paused",
            })
        return jobs
