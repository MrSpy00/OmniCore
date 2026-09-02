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

_QUERY_DOMAIN_HINTS: tuple[tuple[str, str], ...] = (
    ("dosya", "filesystem"),
    ("file", "filesystem"),
    ("klasor", "filesystem"),
    ("path", "filesystem"),
    ("terminal", "devops"),
    ("bash", "devops"),
    ("powershell", "devops"),
    ("deploy", "devops"),
    ("network", "network"),
    ("ag", "network"),
    ("internet", "network"),
    ("api", "network"),
    ("web", "browser"),
    ("browser", "browser"),
    ("tarayici", "browser"),
    ("ekran", "ui"),
    ("gui", "ui"),
    ("click", "ui"),
    ("vision", "vision"),
    ("ocr", "vision"),
    ("resim", "media"),
    ("video", "media"),
    ("ses", "media"),
    ("process", "process"),
    ("surec", "process"),
    ("security", "security"),
    ("guvenlik", "security"),
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

_DELEGATION_MARKERS = (
    "scan directory",
    "scan files",
    "grep code",
    "scan codebase",
    "find in code",
    "search code",
)

# Tools that should NEVER be delegated to swarm — they are specific actions
_NON_DELEGATABLE_PREFIXES = (
    "web_",
    "browser_",
    "gui_",
    "os_",
    "terminal_",
    "dev_execute",
    "media_",
    "sys_",
    "security_",
    "hardware_",
    "game_",
    "steam_",
    "audio_",
    "network_",
)


def infer_tool_domain(tool_name: str) -> str:
    lowered = (tool_name or "").lower()
    for prefix, domain in _DOMAIN_HINTS:
        if lowered.startswith(prefix) or prefix in lowered:
            return domain
    return "general"


def infer_query_domains(query: str) -> set[str]:
    lowered = (query or "").lower()
    matches: set[str] = set()
    for marker, domain in _QUERY_DOMAIN_HINTS:
        if marker in lowered:
            matches.add(domain)
    return matches


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
            domain = raw.get("domain") or infer_tool_domain(tool_name)
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
                delegated=bool(raw.get("delegated", False)),
                delegation_strategy=str(raw.get("delegation_strategy", "none") or "none"),
            )
            self._annotate_delegation(step)
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

    def replan_failed_step(
        self,
        plan: TaskPlan,
        failed_step_index: int,
        failure_reason: str,
    ) -> TaskPlan:
        """Self-healing replanner: adapt remaining steps if a step fails."""
        if failed_step_index < 0 or failed_step_index >= len(plan.steps):
            return plan

        failed_step = plan.steps[failed_step_index]
        logger.warning(
            "planner.replan_triggered",
            plan_id=plan.id,
            failed_step=failed_step.description,
            reason=failure_reason[:100],
        )

        # Build recovery step
        recovery_step = TaskStep(
            tool_name="dev_grep_analyzer",
            description=f"Self-healing diagnostic for failed step: {failed_step.description}",
            parameters={"query": failure_reason[:50]},
            domain="devops",
            risk_level=RiskLevel.LOW,
        )

        new_steps = (
            list(plan.steps[:failed_step_index])
            + [recovery_step]
            + list(plan.steps[failed_step_index:])
        )
        return TaskPlan(
            user_request=plan.user_request,
            steps=new_steps,
        )

    @staticmethod
    def _annotate_delegation(step: TaskStep) -> None:
        if step.delegated:
            return

        lowered_tool = (step.tool_name or "").lower()

        # Never delegate specific action tools (web, gui, browser, etc.)
        if any(lowered_tool.startswith(prefix) for prefix in _NON_DELEGATABLE_PREFIXES):
            return

        # Only delegate when description explicitly matches codebase scan patterns
        lowered_desc = (step.description or "").lower()
        if any(marker in lowered_desc for marker in _DELEGATION_MARKERS):
            step.delegated = True
            step.delegation_strategy = "swarm"
