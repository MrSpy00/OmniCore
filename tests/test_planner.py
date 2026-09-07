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
                    "description": "grep code for TODO strings",
                    "parameters": {"pattern": "TODO"},
                }
            ],
        )
        step = plan.steps[0]
        assert step.delegated is True
        assert step.delegation_strategy == "swarm"

    def test_does_not_delegate_web_tools(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan(
            "Open YouTube",
            [
                {
                    "tool": "web_play_youtube_video_visible",
                    "description": "YouTube'da video ara ve ac",
                    "parameters": {"query": "test"},
                }
            ],
        )
        step = plan.steps[0]
        assert step.delegated is False

    def test_does_not_delegate_gui_tools(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan(
            "Take screenshot",
            [
                {
                    "tool": "gui_analyze_screen",
                    "description": "Ekran goruntusu al",
                    "parameters": {},
                }
            ],
        )
        step = plan.steps[0]
        assert step.delegated is False

    def test_replan_failed_step(self):
        planner = Planner(llm=None)  # type: ignore[arg-type]
        plan = planner.build_plan(
            "Test plan",
            [
                {"tool": "os_read_file", "description": "Read config", "parameters": {}},
                {"tool": "os_write_file", "description": "Write backup", "parameters": {}},
            ],
        )
        replanned = planner.replan_failed_step(plan, failed_step_index=0, failure_reason="File not found")
        assert len(replanned.steps) == 3
        assert replanned.steps[0].tool_name == "dev_grep_analyzer"
        assert "Self-healing diagnostic" in replanned.steps[0].description


class TestWorkflowExecutionEngine:
    """Test checkpointing and alternative branching recovery."""

    def test_checkpoint_and_load(self, tmp_path):
        from core.planner import WorkflowExecutionEngine

        db_file = tmp_path / "test_wf.db"
        engine = WorkflowExecutionEngine(db_path=db_file)

        engine.checkpoint_step("wf-1", 0, "os_read_file", "completed", {"path": "a.txt"}, {"content": "ok"})
        checkpoints = engine.get_completed_steps("wf-1")

        assert 0 in checkpoints
        assert checkpoints[0]["tool"] == "os_read_file"
        assert checkpoints[0]["status"] == "completed"

    def test_suggest_alternative_branch(self, tmp_path):
        from core.planner import WorkflowExecutionEngine

        engine = WorkflowExecutionEngine(db_path=tmp_path / "test_wf.db")

        # File not found
        tool, params = engine.suggest_alternative_branch("os_read_file", "Error: File not found")
        assert tool == "es_fast_search"

        # Web blocked
        tool, params = engine.suggest_alternative_branch("web_scrape", "net::ERR_CONNECTION_TIMED_OUT")
        assert tool == "browser_fetch_page"

        # General failure
        tool, params = engine.suggest_alternative_branch("terminal_execute", "syntax error")
        assert tool == "terminal_execute"


class TestTreeOfThoughtPlanner:
    """Test heuristic branch evaluation and selection."""

    def test_score_branch_and_select_best(self):
        from types import SimpleNamespace

        from core.planner import TreeOfThoughtPlanner
        from models.tasks import TaskStep

        tot = TreeOfThoughtPlanner(llm=None, n_candidates=2)

        # Branch A: 1 low risk step
        branch_a = SimpleNamespace(
            steps=[TaskStep(tool_name="os_read_file", description="read file", risk_level=RiskLevel.LOW)]
        )
        # Branch B: 5 critical destructive steps
        branch_b = SimpleNamespace(
            steps=[
                TaskStep(
                    tool_name="os_delete_file",
                    description=f"del {i}",
                    is_destructive=True,
                    risk_level=RiskLevel.CRITICAL,
                )
                for i in range(5)
            ]
        )

        score_a = tot.score_branch(branch_a)
        score_b = tot.score_branch(branch_b)
        assert score_a > score_b

        best = tot.select_best([branch_a, branch_b])
        assert best is branch_a
        assert getattr(best, "selected", False) is True
