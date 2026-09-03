"""Scheduler Toolkit — dynamic reminder injection."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class SchedAddDynamicReminder(BaseTool):
    name = "sched_add_dynamic_reminder"
    description = "Schedule a one-off reminder to send a Telegram message."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        from memory.state import StateTracker

        remind_at = tool_input.parameters.get("remind_at")
        user_id = tool_input.parameters.get("user_id")
        text = tool_input.parameters.get("text", "")
        if not remind_at or not user_id or not text:
            return self._failure("remind_at, user_id, and text are required")

        try:
            dt = datetime.fromisoformat(remind_at)
        except (ValueError, TypeError):
            return self._failure(
                f"Invalid remind_at format: {remind_at}. Use ISO format (e.g. 2025-07-15T10:00:00+03:00)."
            )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        cron_expr = f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"

        try:
            job_id = f"reminder_{uuid.uuid4().hex[:8]}"
            config_json = json.dumps({"prompt": text, "user_id": str(user_id)})

            tracker = StateTracker()
            await tracker.initialize()
            await tracker.save_scheduled_job(
                job_id=job_id,
                job_name="One-off Reminder",
                cron_expr=cron_expr,
                enabled=True,
                config_json=config_json,
            )
            await tracker.close()

            return self._success("Reminder scheduled", data={"job_id": job_id, "cron": cron_expr})
        except Exception as exc:
            return self._failure(str(exc))
