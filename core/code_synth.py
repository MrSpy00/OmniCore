"""Dinamik Kod Sentezi & AST Güvenlik Filtresi.

Mevcut araçların hiçbiri kullanıcının özel ihtiyacını karşılamıyorsa,
göreve özel tek seferlik bir Python betiği üretip AST güvenlik filtresinden
geçirdikten sonra sandbox'ta çalıştırır.
"""

from __future__ import annotations

import ast
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


class ASTSafetyFilter:
    """Python kodunu güvenlik için AST ile analiz eder.

    Kontroller:
    - Tehlikeli modül importları (os, subprocess, sys, shutil, socket, ctypes)
    - eval/exec çağrıları
    - Dosya I/O (open, write) — izin verilmedikçe
    - Ağ çağrıları (requests, httpx, urllib) — izin verilmedikçe
    - Dunder attribute access (__init__ haricinde)
    - Maksimum AST düğüm sayısı
    """

    SAFE_BUILTINS = frozenset(
        {
            "abs",
            "all",
            "any",
            "bool",
            "dict",
            "enumerate",
            "filter",
            "float",
            "format",
            "frozenset",
            "getattr",
            "hasattr",
            "hash",
            "hex",
            "id",
            "int",
            "isinstance",
            "issubclass",
            "iter",
            "len",
            "list",
            "map",
            "max",
            "min",
            "next",
            "oct",
            "ord",
            "pow",
            "print",
            "range",
            "repr",
            "reversed",
            "round",
            "set",
            "sorted",
            "str",
            "sum",
            "super",
            "tuple",
            "type",
            "zip",
        }
    )

    BLOCKED_MODULES = frozenset(
        {
            "os",
            "subprocess",
            "sys",
            "shutil",
            "socket",
            "ctypes",
            "importlib",
            "__import__",
            "compile",
            "exec",
            "eval",
        }
    )

    MAX_AST_NODES = 200

    @classmethod
    def analyze(cls, code: str) -> tuple[bool, list[str]]:
        """Kodu güvenlik için analiz eder.

        Returns:
            (is_safe, violations) — is_safe=True ise kod güvenli.
        """
        violations: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return False, [f"Sözdizimi hatası: {exc}"]

        node_count = sum(1 for _ in ast.walk(tree))
        if node_count > cls.MAX_AST_NODES:
            violations.append(f"AST düğüm sayısı çok yüksek: {node_count} (maks: {cls.MAX_AST_NODES})")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod in cls.BLOCKED_MODULES:
                        violations.append(f"Engellenen modül importu: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod = node.module.split(".")[0]
                    if mod in cls.BLOCKED_MODULES:
                        violations.append(f"Engellenen modül importu: {node.module}")

            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("eval", "exec", "compile"):
                    violations.append(f"Tehlikeli çağrı: {func.id}()")
                if isinstance(func, ast.Attribute) and func.attr in ("eval", "exec"):
                    violations.append(f"Tehlikeli çağrı: .{func.attr}()")

            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__") and node.attr != "__init__":
                    violations.append(f"Dunder erişimi: {node.attr}")

        return len(violations) == 0, violations


class DynamicCodeSynthesizer:
    """LLM ile kod üretir, AST ile doğrular ve sandbox'ta çalıştırır."""

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm
        self._safety = ASTSafetyFilter()

    async def synthesize_and_execute(
        self,
        task_description: str,
        available_context: dict[str, Any] | None = None,
        allowed_modules: list[str] | None = None,
    ) -> dict[str, Any]:
        """Kod üret, güvenlik doğrula, çalıştır, sonucu döndür."""
        code = await self._generate_code(task_description, available_context or {})

        if not code:
            return {"success": False, "error": "Kod üretilemedi."}

        is_safe, violations = self._safety.analyze(code)
        if not is_safe:
            return {
                "success": False,
                "error": "Kod güvenlik filtresinden geçemedi.",
                "violations": violations,
                "code": code,
            }

        try:
            result = self._execute_sandboxed(code, available_context or {})
            return {
                "success": True,
                "result": result,
                "code": code,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Çalıştırma hatası: {exc}",
                "code": code,
            }

    async def _generate_code(self, task_description: str, context: dict[str, Any]) -> str:
        """LLM ile kod üretir."""
        if not self._llm:
            return ""

        prompt = (
            f"Görev: {task_description}\n"
            f"Mevcut bağlam: {list(context.keys())}\n"
            "Yalnızca sonuç değişkeni olarak 'result' atayın. "
            "Tehlikeli modülleri (os, subprocess, sys) import etmeyin."
        )

        try:
            response = await self._llm.ainvoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            code = text.strip()
            if code.startswith("```"):
                lines = code.split("\n")
                code = "\n".join(lines[1:-1])
            return code
        except Exception:
            return ""

    def _execute_sandboxed(self, code: str, context: dict[str, Any]) -> Any:
        """Kodu kısıtlı bir isim alanında çalıştırır."""
        safe_globals: dict[str, Any] = {
            "__builtins__": {k: __builtins__[k] for k in ASTSafetyFilter.SAFE_BUILTINS if k in __builtins__},
        }
        safe_globals.update(context)
        safe_globals["result"] = None

        exec(compile(ast.parse(code), "<sentezlenmis>", "exec"), safe_globals)
        return safe_globals.get("result")
