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
    """Execute tools with automatic retry and error analysis.

    Parameters
    ----------
    max_attempts:
        Maximum number of execution attempts per tool call (default: 2).
        Override via ``RECOVERY_MAX_ATTEMPTS`` in ``.env`` or by passing
        ``get_settings().recovery_max_attempts`` to the constructor.
    """

    def __init__(
        self,
        max_attempts: int = _MAX_RETRY_CAP,
        timeout_seconds: float = 120.0,
        max_retry_cap: int | None = None,
    ) -> None:
        if max_retry_cap is not None:
            max_attempts = max_retry_cap
        self._max_retry_cap = max(1, max_attempts)
        self._timeout_seconds = max(0.01, timeout_seconds)

    async def execute_with_retry(
        self,
        tool: BaseTool,
        tool_input: ToolInput,
        step: TaskStep,
    ) -> ToolOutput:
        """Attempt to execute *tool* up to 2 times (hard cap).

        On each failure the engine waits with exponential backoff before
        retrying. The ``step.retry_count`` is updated in-place.
        Applies a timeout per attempt to prevent hanging executions.
        """
        last_output: ToolOutput | None = None
        effective_max = max(1, min(step.max_retries, self._max_retry_cap))

        for attempt in range(effective_max + 1):
            try:
                output = await asyncio.wait_for(
                    tool.execute(tool_input),
                    timeout=self._timeout_seconds,
                )
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
                err_msg = output.error or "Unknown error"
                logger.warning(
                    "recovery.tool_returned_failure",
                    tool=tool.name,
                    attempt=attempt + 1,
                    error=err_msg[:300],
                )

                # Loop-breaker: stop when all retries are exhausted.
                if attempt >= effective_max:
                    logger.warning(
                        "recovery.loop_breaker_triggered",
                        tool=tool.name,
                        reason="max_retries_exhausted",
                    )
                    last_output.error = (
                        f"[LOOP_PROTECTION] Tool '{tool.name}' failed after {attempt + 1} attempts. "
                        f"Last error: {err_msg}"
                    )
                    return last_output

            except TimeoutError:
                err_msg = f"Tool '{tool.name}' timed out after {self._timeout_seconds}s"
                logger.error(
                    "recovery.tool_timeout",
                    tool=tool.name,
                    attempt=attempt + 1,
                    timeout=self._timeout_seconds,
                )
                last_output = ToolOutput(
                    tool_name=tool.name,
                    status=ToolStatus.FAILURE,
                    error=err_msg,
                )
                step.retry_count = attempt + 1

                if attempt >= effective_max:
                    logger.warning(
                        "recovery.loop_breaker_triggered",
                        tool=tool.name,
                        reason="max_retries_exhausted_timeout",
                    )
                    last_output.error = f"[LOOP_PROTECTION] Tool '{tool.name}' timed out after {attempt + 1} attempts."
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

                if attempt >= effective_max:
                    logger.warning(
                        "recovery.loop_breaker_triggered",
                        tool=tool.name,
                        reason="max_retries_exhausted_exception",
                    )
                    last_output.error = (
                        f"[LOOP_PROTECTION] Tool '{tool.name}' raised an unhandled exception after "
                        f"{attempt + 1} attempts. Error: {type(exc).__name__}: {exc}"
                    )
                    return last_output

            # Exponential backoff before next attempt.
            if attempt < effective_max:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.debug("recovery.backoff", delay=delay)
                await asyncio.sleep(delay)

        if last_output:
            return last_output
        return ToolOutput(
            tool_name=tool.name,
            status=ToolStatus.FAILURE,
            error=(
                f"[LOOP_PROTECTION] Tool '{tool.name}': "
                f"All retries exhausted ({effective_max} attempts), no result obtained."
            ),
        )
