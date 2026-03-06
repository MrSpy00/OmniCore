"""Recovery Engine — error handling, retry, and fallback logic.

When a tool execution fails, the RecoveryEngine:
  1. Logs the error with full context.
  2. Checks whether retries remain (hard cap: 2 attempts max).
  3. Re-attempts the tool call (up to ``step.max_retries``, capped at 2).
  4. If all retries are exhausted, returns a Turkish failure message.
"""

from __future__ import annotations

import asyncio
import traceback

from config.logging import get_logger
from models.tasks import TaskStep
from models.tools import ToolInput, ToolOutput, ToolStatus
from tools.base import BaseTool

logger = get_logger(__name__)

# Backoff base delay between retries (seconds).
_RETRY_BASE_DELAY = 2.0

# Hard cap: never retry more than 2 times regardless of step.max_retries.
_MAX_RETRY_CAP = 2


class RecoveryEngine:
    """Execute tools with automatic retry and error analysis."""

    async def execute_with_retry(
        self,
        tool: BaseTool,
        tool_input: ToolInput,
        step: TaskStep,
    ) -> ToolOutput:
        """Attempt to execute *tool* up to 2 times (hard cap).

        On each failure the engine waits with exponential backoff before
        retrying.  The ``step.retry_count`` is updated in-place.
        After 2 consecutive failures, returns a Turkish error message.
        """
        last_output: ToolOutput | None = None
        effective_max = min(step.max_retries, _MAX_RETRY_CAP)

        for attempt in range(effective_max + 1):
            try:
                output = await tool.execute(tool_input)
                if output.status == ToolStatus.SUCCESS:
                    if attempt > 0:
                        logger.info(
                            "recovery.succeeded_on_retry",
                            tool=tool.name,
                            attempt=attempt + 1,
                        )
                    return output

                # Tool returned a non-success status — treat as retriable.
                last_output = output
                step.retry_count = attempt + 1
                logger.warning(
                    "recovery.tool_returned_failure",
                    tool=tool.name,
                    attempt=attempt + 1,
                    error=output.error[:300],
                )

                # Loop-breaker: stop early after 2 consecutive failures.
                if attempt >= 1:
                    logger.warning(
                        "recovery.loop_breaker_triggered",
                        tool=tool.name,
                        reason="2_ardisik_basarisizlik",
                    )
                    last_output.error = (
                        f"[DÖNGÜ KORUMASI] {tool.name} araci 2 kez basarisiz oldu. "
                        f"Son hata: {last_output.error}"
                    )
                    return last_output

            except Exception as exc:
                tb = traceback.format_exc()
                logger.error(
                    "recovery.exception",
                    tool=tool.name,
                    attempt=attempt + 1,
                    error=str(exc),
                    traceback=tb[:500],
                )
                last_output = ToolOutput(
                    tool_name=tool.name,
                    status=ToolStatus.FAILURE,
                    error=f"{type(exc).__name__}: {exc}",
                )
                step.retry_count = attempt + 1

                if attempt >= 1:
                    logger.warning(
                        "recovery.loop_breaker_triggered",
                        tool=tool.name,
                        reason="2_ardisik_istisna",
                    )
                    last_output.error = (
                        f"[DÖNGÜ KORUMASI] {tool.name} araci 2 kez istisna firlatarak basarisiz oldu. "
                        f"Son hata: {type(exc).__name__}: {exc}"
                    )
                    return last_output

            # Exponential backoff before next attempt.
            if attempt < effective_max:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.debug("recovery.backoff", delay=delay)
                await asyncio.sleep(delay)

        logger.error(
            "recovery.all_retries_exhausted",
            tool=tool.name,
            retries=effective_max,
        )
        return last_output or ToolOutput(
            tool_name=tool.name,
            status=ToolStatus.FAILURE,
            error=f"[DÖNGÜ KORUMASI] {tool.name}: Tum denemeler tukendi, sonuc alinamadi.",
        )
