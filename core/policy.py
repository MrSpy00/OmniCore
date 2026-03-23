"""Policy engine for capability governance and execution safety."""

from __future__ import annotations

from typing import Any

from models.capabilities import GovernancePolicy, PolicyDecision, RiskLevel
from models.tasks import TaskStep


class CapabilityPolicyEngine:
    """Evaluate a task step against governance controls.

    Rules implemented:
    - Deny known destructive command patterns.
    - Require dry-run for high/critical risk.
    - Require confirmation for high risk.
    - Require double confirmation + backup for critical risk.
    - Require explicit admin verification when requested by step metadata.
    """

    def __init__(self, policy: GovernancePolicy | None = None) -> None:
        self._policy = policy or GovernancePolicy()

    def evaluate(self, step: TaskStep) -> PolicyDecision:
        decision = PolicyDecision()
        risk = RiskLevel(step.risk_level)

        flat_params = self._flatten_params(step.parameters)
        if self._apply_blocking_rules(flat_params, decision):
            return decision

        self._apply_risk_rules(step, risk, decision)
        self._apply_admin_rule(step, decision)
        self._apply_fallback_safe_response(decision)

        return decision

    def _apply_blocking_rules(self, flat_params: str, decision: PolicyDecision) -> bool:
        block_category = self._detect_defensive_category(flat_params)
        if block_category:
            decision.allowed = False
            decision.reasons.append(self._category_reason(block_category))
            decision.blocked_category = block_category
            decision.safe_response = self._policy.safe_response_templates.get(block_category, "")
            return True

        if self._contains_deny_pattern(flat_params):
            decision.allowed = False
            decision.reasons.append("command_matches_deny_pattern")
            decision.blocked_category = "destructive"
            decision.safe_response = self._policy.safe_response_templates.get("destructive", "")
            return True
        return False

    @staticmethod
    def _category_reason(category: str) -> str:
        if category == "privilege_escalation":
            return "privilege_escalation_block"
        if category == "persistence_abuse":
            return "persistence_abuse_block"
        if category == "stealth_memory_abuse":
            return "stealth_memory_abuse_block"
        if category == "kernel_manipulation":
            return "kernel_manipulation_block"
        if category == "raw_disk_access":
            return "raw_disk_access_block"
        if category == "network_spoofing":
            return "network_spoofing_block"
        if category == "reverse_engineering_abuse":
            return "reverse_engineering_abuse_block"
        return "defensive_only_block"

    def _apply_risk_rules(self, step: TaskStep, risk: RiskLevel, decision: PolicyDecision) -> None:
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            decision.require_dry_run = True
            if not step.dry_run_done:
                decision.allowed = False
                decision.reasons.append("missing_dry_run")

        if risk == RiskLevel.HIGH:
            decision.require_confirmation = True

        if risk == RiskLevel.CRITICAL:
            decision.require_confirmation = True
            decision.require_double_confirmation = True
            decision.require_backup = True
            if not step.backup_ready:
                decision.allowed = False
                decision.reasons.append("backup_required")

    @staticmethod
    def _apply_admin_rule(step: TaskStep, decision: PolicyDecision) -> None:
        if step.requires_admin and not step.admin_verified:
            decision.allowed = False
            decision.reasons.append("admin_verification_required")

    def _apply_fallback_safe_response(self, decision: PolicyDecision) -> None:
        if decision.allowed or decision.safe_response:
            return
        decision.blocked_category = decision.blocked_category or "destructive"
        decision.safe_response = self._policy.safe_response_templates.get("destructive", "")

    def _contains_deny_pattern(self, flat_params: str) -> bool:
        haystack = flat_params.lower()
        return any(pattern in haystack for pattern in self._policy.deny_patterns)

    def _contains_defensive_only_marker(self, flat_params: str) -> bool:
        haystack = flat_params.lower()
        return any(marker in haystack for marker in self._policy.defensive_only_markers)

    def _detect_defensive_category(self, flat_params: str) -> str:
        haystack = flat_params.lower()
        if any(marker in haystack for marker in self._policy.privilege_escalation_markers):
            return "privilege_escalation"
        if any(marker in haystack for marker in self._policy.persistence_markers):
            return "persistence_abuse"
        if any(marker in haystack for marker in self._policy.stealth_memory_markers):
            return "stealth_memory_abuse"
        if any(marker in haystack for marker in self._policy.kernel_manipulation_markers):
            return "kernel_manipulation"
        if any(marker in haystack for marker in self._policy.raw_disk_access_markers):
            return "raw_disk_access"
        if any(marker in haystack for marker in self._policy.network_spoofing_markers):
            return "network_spoofing"
        if any(marker in haystack for marker in self._policy.reverse_engineering_markers):
            return "reverse_engineering_abuse"
        if self._contains_defensive_only_marker(flat_params):
            return "defensive_only"
        return ""

    @staticmethod
    def _flatten_params(parameters: dict[str, Any]) -> str:
        chunks: list[str] = []
        for key, value in parameters.items():
            chunks.append(str(key))
            chunks.append(str(value))
        return " ".join(chunks)
