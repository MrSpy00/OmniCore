"""Tests for the scheduler (unit-level, no real scheduling)."""

from __future__ import annotations

from scheduler.jobs import BUILTIN_JOBS


class TestBuiltinJobs:
    def test_builtin_jobs_have_required_fields(self):
        for job in BUILTIN_JOBS:
            assert "id" in job
            assert "name" in job
            assert "cron" in job
            assert "prompt" in job

    def test_morning_briefing_exists(self):
        ids = [j["id"] for j in BUILTIN_JOBS]
        assert "morning_briefing" in ids
