"""DevOps and code engineering toolkit."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.base import resolve_user_path


class DevGitCommitPush(BaseTool):
    name = "dev_git_commit_push"
    description = "Stage, commit, and push git changes in a target repository path."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        message = str(
            self._first_param(params, "message", "commit_message", default="Update project")
        )
        repo_path_raw = str(self._first_param(params, "repo_path", "path", "cwd", default="."))
        try:
            repo_path = resolve_user_path(repo_path_raw)[0]
            result = await asyncio.to_thread(_git_commit_push, message, repo_path)
            return self._success("Git commit/push completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class DevRunPytestSuite(BaseTool):
    name = "dev_run_pytest_suite"
    description = "Run the pytest suite and return raw logs."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                ["uv", "run", "pytest", "-v"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            return self._success(
                "Pytest suite executed",
                data={
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "returncode": completed.returncode,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class DevLintAndFormat(BaseTool):
    name = "dev_lint_and_format"
    description = "Run black and flake8 on a file or directory."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        target = str(self._first_param(params, "target", "path", default="."))
        try:
            result = await asyncio.to_thread(_lint_and_format, target)
            return self._success("Lint/format completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


class DevDockerManage(BaseTool):
    name = "dev_docker_manage"
    description = "Run docker or docker-compose commands."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", default="ps"))
        try:
            result = await asyncio.to_thread(_docker_manage, action)
            return self._success("Docker command completed", data=result)
        except Exception as exc:
            return self._failure(str(exc))


def _git_commit_push(message: str, repo_path: Path) -> dict[str, object]:
    if not repo_path.exists() or not repo_path.is_dir():
        raise RuntimeError(f"Repository path not found: {repo_path}")

    commands = [
        ["git", "add", "."],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    last_output = ""
    steps: list[dict[str, str | int]] = []
    for cmd in commands:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(repo_path),
        )
        last_output = completed.stdout + completed.stderr
        steps.append(
            {
                "command": " ".join(cmd),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(last_output)
    return {"output": last_output, "repo_path": str(repo_path), "steps": steps}


def _lint_and_format(target: str) -> dict[str, str]:
    black = subprocess.run(["black", target], capture_output=True, text=True, timeout=120)
    flake = subprocess.run(["flake8", target], capture_output=True, text=True, timeout=120)
    return {"black": black.stdout + black.stderr, "flake8": flake.stdout + flake.stderr}


def _docker_manage(action: str) -> dict[str, str | int]:
    if action == "ps":
        completed = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=60)
    elif action in {"up", "down"}:
        command = ["docker-compose", action]
        if action == "up":
            command.append("-d")
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    else:
        raise ValueError("Unsupported docker action")
    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }
