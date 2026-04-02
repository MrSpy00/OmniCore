"""Planner — multi-step plan generator and validator.

The Planner takes raw step descriptions from the LLM classification and
converts them into a structured ``TaskPlan`` with validated ``TaskStep``
objects.
"""

from __future__ import annotations

from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from config.logging import get_logger
from models.capabilities import RiskLevel
from models.tasks import TaskPlan, TaskStep

logger = get_logger(__name__)

# Tools that are inherently destructive and always require HITL approval.
_DESTRUCTIVE_TOOLS = frozenset(
    {
        "os_write_file",
        "os_move_file",
        "os_delete_file",
        "terminal_execute",
    }
)

_DOMAIN_HINTS: tuple[tuple[str, str], ...] = (
    ("os_", "filesystem"),
    ("file", "filesystem"),
    ("sys_", "system"),
    ("process", "process"),
    ("terminal_", "devops"),
    ("net_", "network"),
    ("api_", "network"),
    ("gui_", "ui"),
    ("media_", "media"),
    ("vision", "vision"),
    ("web_", "browser"),
    ("security", "security"),
)

_CRITICAL_RISK_MARKERS = (
    "delete",
    "shutdown",
    "kill",
    "terminate",
    "format",
    "encrypt",
    "registry_delete",
    "reg_delete",
)

_HIGH_RISK_MARKERS = (
    "write",
    "move",
    "set",
    "restart",
    "deploy",
    "registry",
    "reg_",
    "process_",
)


def _infer_domain(tool_name: str) -> str:
    lowered = (tool_name or "").lower()
    for prefix, domain in _DOMAIN_HINTS:
        if lowered.startswith(prefix) or prefix in lowered:
            return domain
    return "general"


def _infer_risk_level(tool_name: str, is_destructive: bool) -> RiskLevel:
    lowered = (tool_name or "").lower()
    if any(marker in lowered for marker in _CRITICAL_RISK_MARKERS):
        return RiskLevel.CRITICAL
    if any(marker in lowered for marker in _HIGH_RISK_MARKERS):
        return RiskLevel.HIGH
    if is_destructive:
        return RiskLevel.HIGH
    return RiskLevel.LOW


class Planner:
    """Converts raw LLM step output into a validated TaskPlan.

    Parameters
    ----------
    llm:
        The LLM instance used for plan refinement if needed.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        self._llm = llm

    def build_plan(
        self,
        user_request: str,
        raw_steps: list[dict[str, Any]],
    ) -> TaskPlan:
        """Construct a ``TaskPlan`` from the raw step dicts returned by
        the Cognitive Router's intent classification.

        Parameters
        ----------
        user_request:
            The original user message.
        raw_steps:
            List of dicts, each with keys ``tool``, ``description``,
            ``parameters``, and optionally ``destructive``.
        """
        steps: list[TaskStep] = []
        for raw in raw_steps:
            tool_name = raw.get("tool", "unknown")
            is_destructive = raw.get("destructive", tool_name in _DESTRUCTIVE_TOOLS)
            risk_level = raw.get("risk_level") or _infer_risk_level(tool_name, is_destructive)
            domain = raw.get("domain") or _infer_domain(tool_name)
            step = TaskStep(
                tool_name=tool_name,
                description=raw.get("description", ""),
                parameters=raw.get("parameters", {}),
                is_destructive=is_destructive,
                domain=domain,
                risk_level=risk_level,
                requires_admin=bool(raw.get("requires_admin", False)),
                requires_dry_run=bool(raw.get("requires_dry_run", False)),
                requires_backup=bool(raw.get("requires_backup", False)),
                requires_double_confirmation=bool(raw.get("requires_double_confirmation", False)),
                dry_run_done=bool(raw.get("dry_run_done", False)),
                backup_ready=bool(raw.get("backup_ready", False)),
                admin_verified=bool(raw.get("admin_verified", False)),
            )
            steps.append(step)

        plan = TaskPlan(
            user_request=user_request,
            steps=steps,
        )
        logger.info(
            "planner.built",
            plan_id=plan.id,
            step_count=len(steps),
            destructive_count=sum(1 for s in steps if s.is_destructive),
        )
        return plan

    @staticmethod
    def validate_plan(plan: TaskPlan) -> list[str]:
        """Return a list of warnings/issues with the plan (empty = valid).

        This is a lightweight sanity check, not a security boundary.
        """
        issues: list[str] = []
        if not plan.steps:
            issues.append("Plan has no steps")
        for step in plan.steps:
            if step.tool_name == "unknown":
                issues.append(f"Step '{step.description}' has unknown tool")
            if not step.description:
                issues.append(f"Step with tool '{step.tool_name}' has no description")
        return issues
