"""Tool discovery and registration system.

The ``ToolRegistry`` is a singleton-style container.  At startup the
application registers every toolkit and the Cognitive Router queries the
registry by name when it needs to dispatch a tool call.
"""

from __future__ import annotations

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
