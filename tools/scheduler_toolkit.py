"""Scheduler Toolkit — dynamic reminder injection."""

from __future__ import annotations

import json
import uuid

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
            job_id = f"reminder_{uuid.uuid4().hex[:8]}"
            config_json = json.dumps({"prompt": text, "user_id": str(user_id)})

            # Reuse the running scheduler by storing a scheduled job definition.
            tracker = StateTracker()
            await tracker.initialize()
            await tracker.save_scheduled_job(
                job_id=job_id,
                job_name="One-off Reminder",
                cron_expr="0 0 1 1 *",
                enabled=True,
                config_json=config_json,
            )
            await tracker.close()

            return self._success("Reminder scheduled", data={"job_id": job_id})
        except Exception as exc:
            return self._failure(str(exc))
