"""Terminal Toolkit — host shell command execution.

Every command goes through the HITL Guardian (``is_destructive = True``)
because arbitrary shell execution is inherently dangerous.
"""

from __future__ import annotations

import asyncio
import os
import platform
import shutil

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path

logger = get_logger(__name__)

# Hard limit to prevent runaway processes.
_DEFAULT_TIMEOUT_SECONDS = 60


def _build_shell_command(command: str) -> tuple[list[str], str]:
    system = platform.system().lower()

    if os.name == "nt":
        powershell = shutil.which("powershell") or "powershell"
        ps_command = (
            "$OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new(); "
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            f"{command}"
        )
        return (
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_command,
            ],
            "powershell",
        )

    if system == "darwin":
        zsh = shutil.which("zsh")
        if zsh:
            return [zsh, "-lc", command], "zsh"
        bash = shutil.which("bash") or "/bin/bash"
        return [bash, "-lc", command], "bash"

    bash = shutil.which("bash")
    if bash:
        return [bash, "-lc", command], "bash"
    sh = shutil.which("sh") or "/bin/sh"
    return [sh, "-lc", command], "sh"


class TerminalExecute(BaseTool):
    """Execute a shell command on the host OS."""

    name = "terminal_execute"
    description = (
        "Execute a shell command in a host working directory. "
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
            cwd = str(resolve_user_path(str(cwd_param))[0])
        else:
            cwd = str(resolve_user_path(".")[0])

        # Ensure working directory exists.
        os.makedirs(cwd, exist_ok=True)

        logger.info("terminal.execute", command=command, cwd=cwd, timeout=timeout)

        try:
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")
            shell_argv, shell_name = _build_shell_command(command)
            process = await asyncio.create_subprocess_exec(
                *shell_argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
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
                    "shell": shell_name,
                },
            )

        except TimeoutError:
            logger.warning("terminal.timeout", command=command, timeout=timeout)
            return self._failure(f"Command timed out after {timeout}s")
        except Exception as exc:
            return self._failure(str(exc))
