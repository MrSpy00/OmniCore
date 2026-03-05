"""Predefined scheduled job definitions.

Each job is a dict with:
  - ``id``: unique identifier
  - ``name``: human-readable label
  - ``cron``: crontab expression (minute hour day month weekday)
  - ``prompt``: the natural-language instruction fed to the CognitiveRouter

Users can add custom jobs through the Telegram gateway or by inserting
rows into the ``scheduled_jobs`` SQLite table.
"""

BUILTIN_JOBS: list[dict[str, str]] = [
    {
        "id": "morning_briefing",
        "name": "Morning Briefing",
        "cron": "0 8 * * *",  # every day at 08:00
        "prompt": (
            "Give me a morning briefing: today's date, a motivational quote, "
            "and any pending tasks from the task tracker."
        ),
    },
    {
        "id": "sandbox_cleanup",
        "name": "Sandbox Cleanup",
        "cron": "0 3 * * 0",  # every Sunday at 03:00
        "prompt": (
            "List all files in the sandbox directory that are older than 7 days. "
            "Summarise them and ask me if I want to delete any."
        ),
    },
]
