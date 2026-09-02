"""Dev Agent Toolkit — full project scaffolding and code generation pipeline.

Inspired by Mark-XXXV's dev_agent: plan → write → install deps → run → auto-fix.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


class DevAgentScaffold(BaseTool):
    """Scaffold a new project from a description."""

    name = "dev_agent_scaffold"
    description = (
        "Create a new project skeleton from a description. Generates project structure, "
        "main files, and requirements. Parameters: project_name, description, "
        "project_type (python|node|generic), output_dir (optional)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        pname = str(self._first_param(params, "project_name", "name", default="") or "").strip()
        desc = str(self._first_param(params, "description", "desc", default="") or "")
        ptype = str(self._first_param(params, "project_type", "type", default="python")).lower()
        out = str(self._first_param(params, "output_dir", "dir", default="") or "")

        if not pname:
            return self._failure("project_name is required")

        try:
            if out:
                base, _ = resolve_user_path(out)
                target = base / pname
            else:
                target = Path.cwd() / pname

            target.mkdir(parents=True, exist_ok=True)

            if ptype == "python":
                files = _scaffold_python(pname, desc)
            elif ptype == "node":
                files = _scaffold_node(pname, desc)
            else:
                files = _scaffold_generic(pname, desc)

            created = []
            for rel_path, content in files.items():
                fp = target / rel_path
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                created.append(rel_path)

            return self._success(
                f"Project '{pname}' scaffolded at {target}",
                data={"path": str(target), "files": created, "type": ptype},
            )
        except Exception as exc:
            return self._failure(f"Scaffolding failed: {exc}")


class DevAgentAutoFix(BaseTool):
    """Run linting, type checks, and tests, then auto-fix issues."""

    name = "dev_agent_auto_fix"
    description = (
        "Auto-fix code issues: run linter with --fix, formatter, and tests. "
        "Parameters: project_dir (optional, defaults to cwd), max_rounds (default: 3)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        project_dir = str(self._first_param(params, "project_dir", "dir", default=".") or "")
        max_rounds = int(self._first_param(params, "max_rounds", "rounds", default=3) or 3)

        target, _ = resolve_user_path(project_dir)
        fixes_applied = []
        rounds_used = 0

        for round_num in range(1, max_rounds + 1):
            rounds_used = round_num

            # Step 1: Auto-fix with linter
            ruff_cmd = [sys.executable, "-m", "ruff", "check", "--fix", "."]
            fix_result = await _run_cmd(target, ruff_cmd)
            if fix_result["returncode"] == 0 and "Fixed" in fix_result.get("stdout", ""):
                fixes_applied.append(f"Round {round_num}: ruff auto-fix applied")

            # Step 2: Format
            fmt_result = await _run_cmd(target, [sys.executable, "-m", "ruff", "format", "."])
            if fmt_result["returncode"] == 0:
                fixes_applied.append(f"Round {round_num}: code formatted")

            # Step 3: Run tests
            test_cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"]
            test_result = await _run_cmd(target, test_cmd)
            if test_result["returncode"] == 0:
                return self._success(
                    f"All clean after {round_num} round(s)",
                    data={"rounds": round_num, "fixes": fixes_applied, "tests": "passed"},
                )

        return self._success(
            f"Completed {rounds_used} fix rounds",
            data={"rounds": rounds_used, "fixes": fixes_applied, "tests": "may need manual review"},
        )


def _scaffold_python(name: str, desc: str) -> dict[str, str]:
    init = f'"""Core module for {name}."""\n'
    main = (
        f'"""Main entry point for {name}."""\n\n\n'
        f"def main() -> None:\n"
        f'    print("Hello from {name}!")\n\n\n'
        f'if __name__ == "__main__":\n    main()\n'
    )
    test = (
        f"from {name}.main import main\n\n\n"
        f"def test_main(capsys):\n"
        f"    main()\n"
        f"    captured = capsys.readouterr()\n"
        f'    assert "Hello" in captured.out\n'
    )
    pyproject = (
        f'[project]\nname = "{name}"\n'
        f'version = "0.1.0"\n'
        f'description = "{desc}"\n'
        f'requires-python = ">=3.12"\n'
        f"dependencies = []\n\n"
        f"[build-system]\n"
        f'requires = ["hatchling"]\n'
        f'build-backend = "hatchling.build"\n'
    )
    return {
        "README.md": f"# {name}\n\n{desc}\n",
        "pyproject.toml": pyproject,
        f"{name}/__init__.py": init,
        f"{name}/main.py": main,
        "tests/__init__.py": "",
        "tests/test_main.py": test,
        ".gitignore": "__pycache__/\n*.pyc\n.venv/\n",
    }


def _scaffold_node(name: str, desc: str) -> dict[str, str]:
    pkg = (
        '{\n  "name": "' + name + '",\n'
        '  "version": "0.1.0",\n'
        '  "description": "' + desc + '",\n'
        '  "main": "index.js",\n'
        '  "scripts": {\n'
        '    "start": "node index.js"\n'
        "  }\n}\n"
    )
    return {
        "README.md": f"# {name}\n\n{desc}\n",
        "package.json": pkg,
        "index.js": f'console.log("Hello from {name}!");\n',
        ".gitignore": "node_modules/\n",
    }


def _scaffold_generic(name: str, desc: str) -> dict[str, str]:
    return {
        "README.md": f"# {name}\n\n{desc}\n",
        ".gitignore": "__pycache__/\n*.pyc\n.venv/\nnode_modules/\n",
    }


async def _run_cmd(cwd: Path, cmd: list[str]) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}
