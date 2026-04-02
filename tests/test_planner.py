"""Tests for the Planner module."""

from __future__ import annotations

from core.planner import Planner
from models.capabilities import RiskLevel


class TestPlannerBuildPlan:
    """Verify plan construction from raw LLM step dicts."""

    def test_builds_plan_from_raw_steps(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        raw_steps = [
            {
                "tool": "web_search",
                "description": "Search for Python 3.13 release notes",
                "parameters": {"query": "Python 3.13 release notes"},
            },
            {
                "tool": "os_write_file",
                "description": "Save summary to file",
                "parameters": {"path": "summary.md", "content": "..."},
                "destructive": True,
            },
        ]
        plan = planner.build_plan("Find Python release notes", raw_steps)

        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "web_search"
        assert plan.steps[0].is_destructive is False
        assert plan.steps[1].tool_name == "os_write_file"
        assert plan.steps[1].is_destructive is True
        assert plan.user_request == "Find Python release notes"

    def test_empty_steps_produce_empty_plan(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan("Do nothing", [])
        assert len(plan.steps) == 0

    def test_validate_plan_catches_unknown_tools(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan("test", [{"tool": "unknown", "description": "bad step"}])
        issues = Planner.validate_plan(plan)
        assert any("unknown tool" in i for i in issues)

    def test_infers_domain_and_risk(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan(
            "Delete file",
            [
                {
                    "tool": "os_delete_file",
                    "description": "Delete target file",
                    "parameters": {"path": "a.txt"},
                }
            ],
        )
        step = plan.steps[0]
        assert step.domain == "filesystem"
        assert step.risk_level == RiskLevel.CRITICAL

    def test_marks_delegated_strategy_for_search_like_steps(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan(
            "Search code",
            [
                {
                    "tool": "dev_grep_analyzer",
                    "description": "Search TODO strings",
                    "parameters": {"pattern": "TODO"},
                }
            ],
        )
        step = plan.steps[0]
        assert step.delegated is True
        assert step.delegation_strategy == "swarm"
