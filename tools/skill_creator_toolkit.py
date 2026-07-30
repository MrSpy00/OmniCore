"""Skill Creator Toolkit — Self-improving skill creation and dynamic registry integration.

Allows OmniCore to synthesize new reusable Python tool classes at runtime,
saving them under ``workspace/skills/`` and registering them dynamically.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
from pathlib import Path

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

logger = get_logger(__name__)

_SKILLS_DIR = Path("workspace/skills")


def _ensure_skills_dir() -> Path:
    _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    init_file = _SKILLS_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Custom user skills package."""\n', encoding="utf-8")
    return _SKILLS_DIR


class SkillCreate(BaseTool):
    """Synthesize and register a new reusable custom tool/skill."""

    name = "skill_create"
    description = (
        "Create and dynamically register a new reusable Python tool skill. "
        "Parameters: skill_name (alphanumeric identifier), description (purpose), "
        "code (Python code defining a BaseTool subclass)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        skill_name = str(
            self._first_param(params, "skill_name", "name", default="") or ""
        ).strip().lower()
        code = str(self._first_param(params, "code", "script", default="") or "").strip()

        if not skill_name or not code:
            return self._failure("skill_name and code parameters are required.")

        # Sanitize name
        clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in skill_name)

        # Validate syntax via AST
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return self._failure(f"Python syntax error in skill code: {exc}")

        skills_dir = _ensure_skills_dir()
        file_path = skills_dir / f"{clean_name}.py"

        try:
            await asyncio.to_thread(file_path.write_text, code, encoding="utf-8")
            logger.info("skill_creator.created", skill_name=clean_name, path=str(file_path))
            return self._success(
                f"Custom skill '{clean_name}' created and saved to {file_path.name}.",
                data={"skill_name": clean_name, "file_path": str(file_path)},
            )
        except Exception as exc:
            return self._failure(f"Failed to write skill file: {exc}")


class SkillList(BaseTool):
    """List all custom user-defined skills in workspace/skills."""

    name = "skill_list"
    description = "List all custom user-defined skills saved in workspace/skills."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        skills_dir = _ensure_skills_dir()
        py_files = list(skills_dir.glob("*.py"))
        skills_info: list[dict[str, str]] = []

        for py in py_files:
            if py.name == "__init__.py":
                continue
            skills_info.append({
                "name": py.stem,
                "file": py.name,
                "size_bytes": str(py.stat().st_size),
            })

        return self._success(
            f"Found {len(skills_info)} custom skills in workspace/skills.",
            data={"skills": skills_info, "count": len(skills_info)},
        )


class SkillExecute(BaseTool):
    """Dynamically load and execute a custom skill by name."""

    name = "skill_execute"
    description = (
        "Execute a custom user-created skill saved in workspace/skills. "
        "Parameters: skill_name (name of skill file), parameters (dict of params)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        skill_name = str(
            self._first_param(params, "skill_name", "name", default="") or ""
        ).strip().lower()

        if not skill_name:
            return self._failure("skill_name parameter is required.")

        skills_dir = _ensure_skills_dir()
        file_path = skills_dir / f"{skill_name}.py"
        if not file_path.exists():
            return self._failure(f"Skill '{skill_name}' not found at {file_path}")

        try:
            tool_instance = await asyncio.to_thread(_load_skill_tool, file_path)
            if tool_instance is None:
                return self._failure(f"No valid BaseTool subclass found in {file_path.name}")

            sub_input = ToolInput(tool_name=tool_instance.name, parameters=params)
            return await tool_instance.execute(sub_input)
        except Exception as exc:
            return self._failure(f"Skill execution failed: {exc}")


def _load_skill_tool(file_path: Path) -> BaseTool | None:
    module_name = f"workspace.skills.{file_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseTool)
            and obj is not BaseTool
        ):
            return obj()
    return None
