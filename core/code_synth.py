"""Dinamik Kod Sentezi & AST Güvenlik Filtresi.

Mevcut araçların hiçbiri kullanıcının özel ihtiyacını karşılamıyorsa,
göreve özel tek seferlik bir Python betiği üretip AST güvenlik filtresinden
geçirdikten sonra sandbox'ta çalıştırır.

Security features:
- AST static analysis blocks dangerous imports and calls
- Restricted builtins (no getattr, type, super, etc.)
- Execution timeout prevents infinite loops
- Maximum AST node limit prevents resource exhaustion
"""

from __future__ import annotations

import ast
import signal
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)

# Maximum execution time in seconds
_MAX_EXECUTION_TIME = 5


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

    # Security: Only include truly safe builtins
    # Explicitly excluded: getattr, hasattr, setattr, delattr, type, super,
    # vars, dir, globals, locals, compile, eval, exec, __import__, open,
    # input, raw_input, breakpoint, exit, quit, memoryview, object,
    # id, hash, callable, isinstance, issubclass, iter, next, repr, format, print
    #
    # Rationale for exclusions:
    # - id/hash: Can be used to probe memory layout
    # - callable/isinstance/issubclass: Can be used to inspect objects
    # - iter/next: Can be used to exhaust resources
    # - repr/format: Can leak internal state
    # - print: Can be used for side-channel attacks
    SAFE_BUILTINS = frozenset(
        {
            "abs",
            "all",
            "any",
            "bin",
            "bool",
            "bytes",
            "chr",
            "complex",
            "dict",
            "divmod",
            "enumerate",
            "filter",
            "float",
            "frozenset",
            "hex",
            "int",
            "len",
            "list",
            "map",
            "max",
            "min",
            "oct",
            "ord",
            "pow",
            "range",
            "reversed",
            "round",
            "set",
            "slice",
            "sorted",
            "str",
            "sum",
            "tuple",
            "zip",
            "True",
            "False",
            "None",
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

    # Dangerous dunder attributes that could lead to sandbox escape
    DANGEROUS_DUNDERS = frozenset(
        {
            "__subclasses__",
            "__bases__",
            "__class__",
            "__globals__",
            "__code__",
            "__loader__",
            "__spec__",
            "__dict__",
            "__weakref__",
            "__module__",
            "__qualname__",
            "__mro__",
            "__subclasshook__",
        }
    )

    # Dangerous builtin functions
    DANGEROUS_BUILTINS = frozenset(
        {
            "eval",
            "exec",
            "compile",
            "__import__",
            "getattr",
            "setattr",
            "delattr",
            "hasattr",
            "vars",
            "dir",
            "globals",
            "locals",
            "type",
            "super",
            "object",
            "open",
            "input",
            "raw_input",
            "breakpoint",
            "exit",
            "quit",
            "memoryview",
        }
    )

    @classmethod
    def analyze(cls, code: str) -> tuple[bool, list[str]]:
        """Kodu güvenlik için analiz eder.

        Returns:
            (is_safe, violations) — is_safe=True ise kod güvenli.
        """
        violations: list[str] = []

        # Security: Limit code size
        if len(code) > 10_000:  # 10KB max
            violations.append(f"Kod çok büyük: {len(code)} bytes (maks: 10000)")
            return False, violations

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
                # Block dangerous builtin calls
                if isinstance(func, ast.Name) and func.id in cls.DANGEROUS_BUILTINS:
                    violations.append(f"Tehlikeli çağrı: {func.id}()")
                # Block attribute-based dangerous calls
                if isinstance(func, ast.Attribute) and func.attr in cls.DANGEROUS_BUILTINS:
                    violations.append(f"Tehlikeli çağrı: .{func.attr}()")

            elif isinstance(node, ast.Attribute):
                # Block dangerous dunder attribute access
                if node.attr in cls.DANGEROUS_DUNDERS:
                    violations.append(f"Tehlikeli dunder erişimi: {node.attr}")
                # Block any dunder except __init__
                elif node.attr.startswith("__") and node.attr.endswith("__") and node.attr != "__init__":
                    violations.append(f"Dunder erişimi: {node.attr}")

            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Block dangerous dunder strings that could be used dynamically
                if node.value in cls.DANGEROUS_DUNDERS:
                    violations.append(f"Tehlikeli dunder string literali: {node.value}")

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
        """Kodu kısıtlı bir isim alanında çalıştırır.

        Uses SIGALRM on Unix to enforce execution timeout.
        On Windows, runs in a thread with timeout.

        Security: __builtins__ is explicitly set to prevent access to dangerous functions.
        """
        import builtins as _builtins_mod

        # Safely extract builtins dict (handles both module and dict forms)
        b_dict: dict[str, Any] = getattr(_builtins_mod, "__dict__", {})
        if not b_dict and isinstance(_builtins_mod, dict):
            b_dict = _builtins_mod

        # Build restricted builtins - only include explicitly safe ones
        restricted_builtins: dict[str, Any] = {}
        for k in ASTSafetyFilter.SAFE_BUILTINS:
            if k in b_dict:
                restricted_builtins[k] = b_dict[k]

        safe_globals: dict[str, Any] = {
            "__builtins__": restricted_builtins,
        }
        safe_globals.update(context)
        safe_globals["result"] = None

        compiled = compile(ast.parse(code), "<sentezlenmis>", "exec")

        # Use timeout mechanism based on platform
        import sys

        if sys.platform == "win32":
            # Windows: run in thread with timeout
            return self._execute_with_timeout(compiled, safe_globals, _MAX_EXECUTION_TIME)
        else:
            # Unix: use SIGALRM
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Code execution exceeded {_MAX_EXECUTION_TIME} seconds")

            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(_MAX_EXECUTION_TIME)
            try:
                exec(compiled, safe_globals)  # nosec B102
                return safe_globals.get("result")
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    def _execute_with_timeout(self, code, globals_dict, timeout):
        """Execute code in a thread with timeout (Windows-compatible)."""
        import threading

        result: list[Any] = [None]
        exception: list[Exception | None] = [None]

        def target():
            try:
                exec(code, globals_dict)  # nosec B102
                result[0] = globals_dict.get("result")
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise TimeoutError(f"Code execution exceeded {timeout} seconds")

        if exception[0] is not None:
            raise exception[0]

        return result[0]
