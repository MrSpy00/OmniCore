"""AST tabanli async hijyen denetimi.

Kontroller:
1) async fonksiyon icinde bloklayici cagri: time.sleep, open, subprocess.*
2) olasi zombie task: await edilmeyen coroutine cagrisi

Karmasiklik: O(F + N), F dosya sayisi, N toplam AST dugumu.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

BLOCKING_NAMES = {"sleep", "open", "run", "Popen", "call", "check_output"}
BLOCKING_MODULES = {"time", "subprocess"}
EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache", ".agents"}


def _iter_py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def _call_name(node: ast.Call) -> tuple[str, str]:
    func = node.func
    if isinstance(func, ast.Name):
        return "", func.id
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return func.value.id, func.attr
        return "", func.attr
    return "", ""


class AsyncAuditVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.async_stack: list[str] = []
        self.issues: list[dict[str, Any]] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.async_stack.append(node.name)
        self.generic_visit(node)
        self.async_stack.pop()

    def visit_Call(self, node: ast.Call) -> Any:
        in_async = bool(self.async_stack)
        mod, name = _call_name(node)

        if in_async and (
            (mod in BLOCKING_MODULES and name in BLOCKING_NAMES) or (mod == "" and name == "open")
        ):
            self.issues.append(
                {
                    "type": "blocking_io_in_async",
                    "file": str(self.file_path).replace("\\", "/"),
                    "line": node.lineno,
                    "function": self.async_stack[-1],
                    "call": f"{mod + '.' if mod else ''}{name}",
                    "suggestion": "Use asyncio.to_thread(...) or async-native alternative.",
                }
            )

        # Zombie task sinyali: coroutine benzeri cagri expression olarak kullanilip
        # degeri yok sayiliyorsa supheli kabul et.
        if in_async and name and name.startswith(("get_", "fetch_", "run_", "execute_")):
            parent = getattr(node, "_parent", None)
            if isinstance(parent, ast.Expr):
                self.issues.append(
                    {
                        "type": "possible_zombie_coroutine",
                        "file": str(self.file_path).replace("\\", "/"),
                        "line": node.lineno,
                        "function": self.async_stack[-1],
                        "call": name,
                        "suggestion": (
                            "Await coroutine or schedule with asyncio.create_task + tracking."
                        ),
                    }
                )

        self.generic_visit(node)


def _annotate_parent(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "_parent", parent)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    issues: list[dict[str, Any]] = []

    for py_file in _iter_py_files(root):
        source = py_file.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        _annotate_parent(tree)
        visitor = AsyncAuditVisitor(py_file)
        visitor.visit(tree)
        issues.extend(visitor.issues)

    print(json.dumps({"issue_count": len(issues), "issues": issues}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
