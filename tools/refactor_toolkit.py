"""Refactor Toolkit — Self-healing code refactorer and patch generator."""

from __future__ import annotations

import ast
import asyncio
import difflib
from pathlib import Path
from typing import Any

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class RefactorAnalyzeFile(BaseTool):
    """Analyze Python code using AST and return metrics and code smells."""

    name = "refactor_analyze_file"
    description = (
        "Analyze Python code using AST and return complexity, function count, and smells. "
        "Parameters: file_path (path to target Python file)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path_str = str(self._first_param(params, "file_path", "path", default="") or "").strip()

        if not path_str:
            return self._failure("file_path parameter is required.")

        target = Path(path_str)
        if not target.exists():
            return self._failure(f"Target file not found: {target}")

        try:
            content = await asyncio.to_thread(target.read_text, encoding="utf-8")
            metrics = await asyncio.to_thread(_analyze_python_ast, content)
            return self._success(
                f"AST analysis of {target.name} complete.",
                data={"file_path": str(target), "metrics": metrics},
            )
        except Exception as exc:
            return self._failure(f"Failed to analyze file: {exc}")


class RefactorGeneratePatch(BaseTool):
    """Generate a unified diff patch replacing target text in a file."""

    name = "refactor_generate_patch"
    description = (
        "Generate a unified diff patch replacing target_text with replacement_text. "
        "Parameters: file_path, target_text, replacement_text."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path_str = str(self._first_param(params, "file_path", "path", default="") or "").strip()
        target_text = str(self._first_param(params, "target_text", "target", default="") or "")
        replacement_text = str(self._first_param(params, "replacement_text", "replacement", default="") or "")

        if not path_str or not target_text:
            return self._failure("file_path and target_text parameters are required.")

        target = Path(path_str)
        if not target.exists():
            return self._failure(f"Target file not found: {target}")

        try:
            content = await asyncio.to_thread(target.read_text, encoding="utf-8")
            if target_text not in content:
                return self._failure("target_text not found in target file.")

            new_content = content.replace(target_text, replacement_text)
            diff = difflib.unified_diff(
                content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{target.name}",
                tofile=f"b/{target.name}",
            )
            patch_str = "".join(diff)

            return self._success(
                f"Unified diff patch generated for {target.name}.",
                data={"patch": patch_str, "file_path": str(target)},
            )
        except Exception as exc:
            return self._failure(f"Failed to generate patch: {exc}")


def _analyze_python_ast(code: str) -> dict[str, Any]:
    tree = ast.parse(code)
    func_count = 0
    class_count = 0
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            func_count += 1
        elif isinstance(node, ast.ClassDef):
            class_count += 1
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return {
        "line_count": len(code.splitlines()),
        "function_count": func_count,
        "class_count": class_count,
        "import_count": len(imports),
        "imports": list(set(imports)),
    }
