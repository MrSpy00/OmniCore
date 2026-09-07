"""Guardian — Human-In-The-Loop (HITL) approval gate.

Intercepts destructive actions, sends an approval request to the user
via the gateway, and blocks until the user approves, denies, or the
request times out.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum

from config.logging import get_logger

logger = get_logger(__name__)


class ApprovalResult(StrEnum):
    """Outcome of an HITL approval request."""

    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


class ApprovalMode(StrEnum):
    """How Guardian handles destructive action approvals."""

    ASK = "ask"
    YES = "yes"
    SAFE = "safe"


ApprovalCallback = Callable[..., Awaitable[ApprovalResult]]


class Guardian:
    """HITL approval gate for destructive actions.

    Parameters
    ----------
    timeout_minutes:
        How long to wait for user approval before auto-aborting.
    approval_callback:
        Async callable provided by the gateway layer.  It receives
        ``(action_description: str, user_id: str)`` and must return an
        ``ApprovalResult``.  If ``None``, all requests auto-approve
        (useful for testing / CLI mode).
    """

    def __init__(
        self,
        timeout_minutes: int = 5,
        approval_callback: Callable[..., Awaitable[ApprovalResult]] | None = None,
        mode: ApprovalMode | str = ApprovalMode.ASK,
    ) -> None:
        self._timeout = timeout_minutes * 60  # convert to seconds
        self._callback = approval_callback
        if isinstance(mode, ApprovalMode):
            self._mode = mode
        else:
            self._mode = ApprovalMode.ASK
            self.set_mode(str(mode))
        self._plan_mode = False

    @property
    def mode(self) -> ApprovalMode:
        return self._mode

    @property
    def plan_mode(self) -> bool:
        return self._plan_mode

    def set_mode(self, mode: str) -> ApprovalMode:
        normalized = (mode or "").strip().lower()
        if normalized in (ApprovalMode.YES.value, "full"):
            self._mode = ApprovalMode.YES
        elif normalized in (ApprovalMode.SAFE.value, "guvenli"):
            self._mode = ApprovalMode.SAFE
        else:
            self._mode = ApprovalMode.ASK
        logger.info("guardian.mode_updated", mode=self._mode.value)
        return self._mode

    def set_plan_mode(self, enabled: bool) -> bool:
        self._plan_mode = bool(enabled)
        logger.info("guardian.plan_mode_updated", enabled=self._plan_mode)
        return self._plan_mode

    def set_approval_callback(self, callback: ApprovalCallback | None) -> None:
        """Set or update the approval callback function."""
        self._callback = callback

    async def request_approval(
        self,
        action_description: str,
        user_id: str = "",
    ) -> ApprovalResult:
        """Request user approval for a destructive action.

        Returns ``ApprovalResult.APPROVED`` if:
          - No callback is set (auto-approve mode).
          - The user explicitly approves within the timeout.

        Returns ``ApprovalResult.DENIED`` if the user explicitly denies.

        Returns ``ApprovalResult.TIMED_OUT`` if the timeout expires.
        """
        if self._mode == ApprovalMode.YES:
            logger.info(
                "guardian.auto_approve_mode",
                action=action_description,
                user_id=user_id,
                mode=self._mode.value,
            )
            return ApprovalResult.APPROVED

        if self._mode == ApprovalMode.SAFE:
            desc_l = action_description.lower()
            # In SAFE mode, only auto-approve explicitly safe (read-only) actions
            safe_keywords = (
                "read",
                "list",
                "show",
                "display",
                "check",
                "search",
                "find",
                "query",
                "get",
                "view",
                "analyze",
                "scan",
            )
            # Destructive keywords that always require approval
            destructive_keywords = (
                "format",
                "disk_wipe",
                "reg_delete",
                "delete_all",
                "shutdown",
                "drop database",
                "rmdir /s",
                "rm -rf /",
                "delete",
                "remove",
                "write",
                "modify",
                "update",
                "create",
                "move",
                "copy",
                "execute",
                "run",
                "install",
                "uninstall",
            )
            is_safe = any(kw in desc_l for kw in safe_keywords)
            is_destructive = any(kw in desc_l for kw in destructive_keywords)
            if is_safe and not is_destructive:
                logger.info(
                    "guardian.safe_mode_auto_approved",
                    action=action_description,
                    user_id=user_id,
                )
                return ApprovalResult.APPROVED
            # Destructive or ambiguous actions require explicit approval in SAFE mode

        if self._callback is None:
            logger.warning(
                "guardian.auto_approve",
                action=action_description,
                reason="no approval callback set",
            )
            return ApprovalResult.APPROVED

        logger.info(
            "guardian.requesting_approval",
            action=action_description,
            user_id=user_id,
            timeout_s=self._timeout,
        )

        try:
            result = await asyncio.wait_for(
                self._callback(action_description, user_id),
                timeout=self._timeout,
            )
            logger.info("guardian.result", action=action_description, result=result)
            return result
        except TimeoutError:
            logger.warning(
                "guardian.timed_out",
                action=action_description,
                timeout_s=self._timeout,
            )
            return ApprovalResult.TIMED_OUT
        except Exception as exc:
            logger.error(
                "guardian.callback_failed",
                action=action_description,
                user_id=user_id,
                error=str(exc),
            )
            return ApprovalResult.DENIED

    async def request_critical_approval(
        self,
        action_description: str,
        user_id: str = "",
    ) -> ApprovalResult:
        """Require two explicit approvals for critical operations."""
        first = await self.request_approval(
            action_description=f"[CRITICAL-1/2] {action_description}",
            user_id=user_id,
        )
        if first != ApprovalResult.APPROVED:
            return first

        second = await self.request_approval(
            action_description=f"[CRITICAL-2/2] {action_description}",
            user_id=user_id,
        )
        return second
