"""Pydantic models for tool inputs and outputs."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ToolStatus(StrEnum):
    """Outcome of a tool execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    NEEDS_APPROVAL = "needs_approval"
    TIMEOUT = "timeout"


class ToolInput(BaseModel):
    """Standardised input envelope for any tool invocation."""

    tool_name: str
    parameters: dict = Field(default_factory=dict)
    requires_approval: bool = False  # set by the guardian before execution


class ToolOutput(BaseModel):
    """Standardised output envelope returned by every tool."""

    tool_name: str
    status: ToolStatus
    result: str = ""  # human-readable summary
    data: dict = Field(default_factory=dict)  # structured output for downstream steps
    error: str = ""  # populated on failure
