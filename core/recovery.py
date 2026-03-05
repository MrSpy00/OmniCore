"""Recovery Engine — error handling, retry, and fallback logic.

When a tool execution fails, the RecoveryEngine:
  1. Logs the error with full context.
  2. Checks whether retries remain.
  3. Re-attempts the tool call (up to ``step.max_retries``).
  4. If all retries are exhausted, returns the failure output.
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


class RecoveryEngine:
    """Execute tools with automatic retry and error analysis."""

    async def execute_with_retry(
        self,
        tool: BaseTool,
        tool_input: ToolInput,
        step: TaskStep,
    ) -> ToolOutput:
        """Attempt to execute *tool* up to ``step.max_retries + 1`` times.

        On each failure the engine waits with exponential backoff before
        retrying.  The ``step.retry_count`` is updated in-place.
        """
        last_output: ToolOutput | None = None

        for attempt in range(step.max_retries + 1):
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

            # Exponential backoff before next attempt.
            if attempt < step.max_retries:
                delay = _RETRY_BASE_DELAY * (2**attempt)
                logger.debug("recovery.backoff", delay=delay)
                await asyncio.sleep(delay)

        logger.error(
            "recovery.all_retries_exhausted",
            tool=tool.name,
            retries=step.max_retries,
        )
        return last_output or ToolOutput(
            tool_name=tool.name,
            status=ToolStatus.FAILURE,
            error="All retries exhausted with no output",
        )
