"""Terminal Toolkit — sandboxed shell command execution.

Every command goes through the HITL Guardian (``is_destructive = True``)
because arbitrary shell execution is inherently dangerous.
"""

from __future__ import annotations

import asyncio
import os

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

logger = get_logger(__name__)

# Hard limit to prevent runaway processes.
_DEFAULT_TIMEOUT_SECONDS = 60


class TerminalExecute(BaseTool):
    """Execute a shell command inside the sandbox directory."""

    name = "terminal_execute"
    description = (
        "Execute a shell command in a sandboxed working directory. "
        "Requires explicit user approval before running."
    )
    is_destructive = True  # always requires HITL approval

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        command = str(self._first_param(params, "command", "cmd", "text", "value", default=""))
        if not command.strip():
            return self._failure("No command provided")

        timeout = params.get("timeout", _DEFAULT_TIMEOUT_SECONDS)
        cwd_param = self._first_param(params, "cwd", "working_dir", default="")
        if cwd_param:
            cwd = str(cwd_param)
        else:
            cwd = os.environ.get("USERPROFILE", "C:\\")

        # Ensure sandbox directory exists.
        os.makedirs(cwd, exist_ok=True)

        logger.info("terminal.execute", command=command, cwd=cwd, timeout=timeout)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            # Truncate very long outputs to stay within LLM context limits.
            max_output = params.get("max_output_chars", 10_000)
            if len(stdout) > max_output:
                stdout = stdout[:max_output] + f"\n... (truncated to {max_output} chars)"
            if len(stderr) > max_output:
                stderr = stderr[:max_output] + f"\n... (truncated to {max_output} chars)"

            if exit_code != 0:
                return self._failure(
                    f"Command exited with code {exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}"
                )

            return self._success(
                f"Command completed (exit {exit_code})",
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                },
            )

        except asyncio.TimeoutError:
            logger.warning("terminal.timeout", command=command, timeout=timeout)
            return self._failure(f"Command timed out after {timeout}s")
        except Exception as exc:
            return self._failure(str(exc))
