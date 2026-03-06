"""Pydantic models for tool inputs and outputs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ToolStatus(StrEnum):
    """Outcome of a tool execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEEDS_APPROVAL = "needs_approval"
    TIMEOUT = "timeout"


class ToolInput(BaseModel):
    """Standardised input envelope for any tool invocation."""

    tool_name: str
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        examples=[
            {"path": "Desktop", "max_bytes": 1000},
            {"file_path": "notes/todo.txt", "content": "hello"},
        ],
    )
    requires_approval: bool = False  # set by the guardian before execution

    @field_validator("parameters", mode="before")
    @classmethod
    def _coerce_parameters(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {
                "value": value,
                "path": value,
                "file_path": value,
                "text": value,
            }
        return {"value": value}


class ToolOutput(BaseModel):
    """Standardised output envelope returned by every tool."""

    tool_name: str
    status: ToolStatus
    result: str = ""  # human-readable summary
    data: dict = Field(default_factory=dict)  # structured output for downstream steps
    error: str = ""  # populated on failure
