"""Guardian — Human-In-The-Loop (HITL) approval gate.

Intercepts destructive actions, sends an approval request to the user
via the gateway, and blocks until the user approves, denies, or the
request times out.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Callable, Awaitable

from config.logging import get_logger

logger = get_logger(__name__)


class ApprovalResult(StrEnum):
    """Outcome of an HITL approval request."""

    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


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
    ) -> None:
        self._timeout = timeout_minutes * 60  # convert to seconds
        self._callback = approval_callback

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
        except asyncio.TimeoutError:
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
