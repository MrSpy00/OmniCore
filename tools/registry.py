"""Tool discovery and registration system.

The ``ToolRegistry`` is a singleton-style container.  At startup the
application registers every toolkit and the Cognitive Router queries the
registry by name when it needs to dispatch a tool call.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
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

    def register(self, tool: BaseTool) -> None:
        """Add a tool to the registry.  Raises on duplicate names."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool
        logger.info("tool_registry.registered", tool=tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by name, or ``None`` if not found."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """Return a list of ``{name, description, destructive}`` dicts.

        This is fed into the LLM system prompt so it knows what tools are
        available.
        """
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
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def discover_tool_classes(tools_package_path: Path) -> list[type[BaseTool]]:
    """Discover all concrete BaseTool subclasses under the tools package."""
    discovered: list[type[BaseTool]] = []
    discovered_names: set[str] = set()
    package_name = "tools"

    for module_info in pkgutil.iter_modules([str(tools_package_path)]):
        module_name = module_info.name
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
