"""Abstract base class that every OmniCore tool must implement.

This ensures a uniform interface for the Cognitive Router to invoke any
tool without knowing its internals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.tools import ToolInput, ToolOutput, ToolStatus


class BaseTool(ABC):
    """Contract that all OmniCore tools must fulfil.

    Subclasses must set ``name`` and ``description`` as class attributes
    and implement the ``execute`` method.  Optionally set
    ``is_destructive = True`` for tools that modify external state.
    """

    # Subclasses override these as plain class attributes.
    name: str = ""
    description: str = ""
    is_destructive: bool = False

    @abstractmethod
    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        """Run the tool with the given parameters and return a result."""

    # -- convenience helpers ---------------------------------------------------

    def _success(self, result: str, data: dict | None = None) -> ToolOutput:
        return ToolOutput(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            result=result,
            data=data or {},
        )

    def _failure(self, error: str) -> ToolOutput:
        return ToolOutput(
            tool_name=self.name,
            status=ToolStatus.FAILURE,
            error=error,
        )
