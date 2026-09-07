"""Tool discovery and registration system.

The ``ToolRegistry`` is a singleton-style container.  At startup the
application registers every toolkit and the Cognitive Router queries the
registry by name when it needs to dispatch a tool call.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import threading
from pathlib import Path

from config.logging import get_logger
from tools.base import BaseTool

logger = get_logger(__name__)


class ToolRegistry:
    """Central catalogue of available tools.

    Usage::

        registry = ToolRegistry()
        registry.register(OsReadFile())
        registry.register(WebSearch())

        tool = registry.get("os_read_file")
        output = await tool.execute(tool_input)
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._lock = threading.RLock()

    def register(self, tool: BaseTool, override: bool = False) -> None:
        """Add a tool to the registry. Raises on duplicate names unless override is True."""
        with self._lock:
            if tool.name in self._tools and not override:
                raise ValueError(f"Tool '{tool.name}' is already registered")
            self._tools[tool.name] = tool
        logger.info("tool_registry.registered", tool=tool.name, overridden=override)

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name, or ``None`` if not found."""
        with self._lock:
            return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """Return a list of ``{name, description, destructive}`` dicts.

        This is fed into the LLM system prompt so it knows what tools are
        available.
        """
        with self._lock:
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "destructive": str(t.is_destructive),
                }
                for t in self._tools.values()
            ]

    @property
    def tool_names(self) -> list[str]:
        with self._lock:
            return list(self._tools.keys())

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._tools


def discover_tool_classes(tools_package_path: Path) -> list[type[BaseTool]]:
    """Discover all concrete BaseTool subclasses under the tools package."""
    import sys

    discovered: list[type[BaseTool]] = []
    discovered_names: set[str] = set()
    package_name = "tools"

    search_paths = [str(tools_package_path)]
    try:
        import tools as _tools_pkg

        if hasattr(_tools_pkg, "__path__"):
            for p in _tools_pkg.__path__:
                if p not in search_paths:
                    search_paths.append(p)
    except Exception:
        pass

    found_modules: set[str] = set()
    for module_info in pkgutil.iter_modules(search_paths):
        found_modules.add(module_info.name)

    # In case of frozen binary where pkgutil cannot find raw files
    if getattr(sys, "frozen", False):
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith("tools.") and not mod_name.endswith((".__init__", ".base", ".registry")):
                found_modules.add(mod_name.split(".", 1)[1])

    for module_name in sorted(found_modules):
        if module_name in {"__init__", "base", "registry"}:
            continue

        try:
            module = importlib.import_module(f"{package_name}.{module_name}")
        except Exception as exc:
            logger.error("tool_registry.import_failed", module=module_name, error=str(exc))
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is BaseTool:
                continue
            if not issubclass(obj, BaseTool):
                continue
            if obj.__module__ != module.__name__:
                continue
            if not getattr(obj, "name", ""):
                continue
            if obj.name in discovered_names:
                logger.warning(
                    "tool_registry.duplicate_discovered_name",
                    tool=obj.name,
                    module=module_name,
                )
                continue
            discovered_names.add(obj.name)
            discovered.append(obj)

    discovered.sort(key=lambda cls: cls.name)
    return discovered


def _validate_skill_ast(code: str) -> tuple[bool, str]:
    """Perform static AST security analysis on custom skill code before execution.

    Blocks:
    - Dangerous module imports (os, subprocess, importlib, ctypes, etc.)
    - Direct calls to eval, exec, __import__, compile
    - Attribute-based calls to dangerous functions (getattr(__builtins__, '__import__'))
    - Dunder attribute access (except __init__)
    - File open() calls that could be used for arbitrary file access
    - Network-related calls (urllib, http, requests, ftplib)
    """
    # Security: Limit code size to prevent abuse
    max_skill_size = 50_000  # 50KB max
    if len(code) > max_skill_size:
        return False, f"Skill file exceeds maximum size of {max_skill_size} bytes"

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error in skill file: {e}"

    blocked_modules = frozenset(
        {
            "os",
            "subprocess",
            "sys",
            "ctypes",
            "socket",
            "pty",
            "shutil",
            "builtins",
            "importlib",
            "runpy",
            "code",
            "codeop",
            "urllib",
            "http",
            "ftplib",
            "smtplib",
            "imaplib",
            "poplib",
            "xmlrpc",
            "requests",
            "aiohttp",
            "httpx",
        }
    )
    blocked_calls = frozenset(
        {
            "eval",
            "exec",
            "__import__",
            "compile",
            "getattr",
            "setattr",
            "delattr",
            "globals",
            "locals",
            "vars",
            "dir",
            "type",
            "open",
            "input",
            "raw_input",
            "breakpoint",
            "exit",
            "quit",
        }
    )
    dunder_pattern = "__"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod in blocked_modules:
                    return False, f"Import of dangerous module '{alias.name}' is blocked"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_mod = node.module.split(".")[0]
                if root_mod in blocked_modules:
                    return False, f"Import from dangerous module '{node.module}' is blocked"
        elif isinstance(node, ast.Call):
            # Direct calls: eval(), exec(), __import__()
            if isinstance(node.func, ast.Name) and node.func.id in blocked_calls:
                return False, f"Direct call to '{node.func.id}' is blocked in custom skills"
            # Attribute calls: getattr(builtins, 'eval')(), obj.__import__()
            if isinstance(node.func, ast.Attribute):
                attr_name = node.func.attr
                if attr_name in blocked_calls:
                    return False, f"Attribute call to '{attr_name}' is blocked"
                if dunder_pattern in attr_name and attr_name != "__init__":
                    return False, f"Dunder attribute access '{attr_name}' is blocked"
        # Block __subclasses__, __bases__, __class__ access
        elif isinstance(node, ast.Attribute):
            dangerous_attrs = (
                "__subclasses__",
                "__bases__",
                "__class__",
                "__globals__",
                "__code__",
                "__loader__",
                "__spec__",
            )
            if node.attr in dangerous_attrs:
                return False, f"Access to dangerous attribute '{node.attr}' is blocked"

    return True, ""


def load_custom_skills(skills_dir: Path) -> list[type[BaseTool]]:
    """Scan and return custom user BaseTool classes under workspace/skills.

    Gated by ENABLE_CUSTOM_SKILLS environment variable (default: disabled).
    Requires explicit opt-in to prevent arbitrary code execution.
    """
    import os

    if os.environ.get("ENABLE_CUSTOM_SKILLS", "").strip().lower() not in ("1", "true", "yes"):
        logger.info("tool_registry.custom_skills_disabled", hint="Set ENABLE_CUSTOM_SKILLS=true to enable")
        return []

    if not skills_dir.exists():
        return []

    # Security: Resolve and validate skills directory to prevent path traversal
    try:
        resolved_skills_dir = skills_dir.resolve()
        # Ensure the skills directory is within expected workspace
        workspace_root = Path(__file__).resolve().parent.parent / "workspace"
        resolved_skills_dir.relative_to(workspace_root)
    except (ValueError, RuntimeError) as exc:
        logger.error("tool_registry.invalid_skills_dir", path=str(skills_dir), error=str(exc))
        return []

    discovered: list[type[BaseTool]] = []
    for py_file in resolved_skills_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue

        # Security: Verify file is within skills directory (prevent symlink traversal)
        try:
            resolved_file = py_file.resolve()
            resolved_file.relative_to(resolved_skills_dir)
        except (ValueError, RuntimeError):
            logger.warning("tool_registry.suspect_skill_path", file=py_file.name)
            continue

        try:
            code = py_file.read_text(encoding="utf-8")
            is_safe, reason = _validate_skill_ast(code)
            if not is_safe:
                logger.warning("tool_registry.custom_skill_unsafe", file=py_file.name, reason=reason)
                continue

            mod_name = f"workspace.skills.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, str(py_file))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if obj is not BaseTool and issubclass(obj, BaseTool) and getattr(obj, "name", ""):
                    discovered.append(obj)
                    logger.info("tool_registry.custom_skill_loaded", tool=obj.name, file=py_file.name)
        except Exception as exc:
            logger.warning("tool_registry.custom_skill_failed", file=py_file.name, error=str(exc))
    return discovered
