"""Pydantic models for tool inputs and outputs."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolStatus(StrEnum):
    """Outcome of a tool execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEEDS_APPROVAL = "needs_approval"
    TIMEOUT = "timeout"


class ToolInput(BaseModel):
    """Standardised input envelope for any tool invocation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tool_name: str = Field(min_length=1, max_length=128)
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
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
            return {
                "value": value,
                "query": value,
                "path": value,
                "file_path": value,
                "content": value,
                "command": value,
                "text": value,
            }
        return {"value": value}

    @field_validator("tool_name", mode="before")
    @classmethod
    def _validate_tool_name(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("tool_name is required")
        return text


class ViewRange(BaseModel):
    """Range metadata for sliced or paged tool outputs."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    start: int = Field(default=0, ge=0)
    end: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    truncated: bool = False


class ToolOutput(BaseModel):
    """Standardised output envelope returned by every tool."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tool_name: str = Field(min_length=1, max_length=128)
    status: ToolStatus
    result: str = ""  # human-readable summary
    data: dict[str, Any] = Field(default_factory=dict)  # structured output for downstream steps
    error: str = ""  # populated on failure
    view_range: ViewRange | None = None

    @field_validator("tool_name", mode="before")
    @classmethod
    def _validate_output_tool_name(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("tool_name is required")
        return text
