"""Tests for the HITL Guardian."""

from __future__ import annotations

import asyncio

import pytest

from core.guardian import ApprovalResult, Guardian


class TestGuardian:
    @pytest.mark.asyncio
    async def test_auto_approves_when_no_callback(self):
        guardian = Guardian(timeout_minutes=1, approval_callback=None)
        result = await guardian.request_approval("delete file", user_id="u1")
        assert result == ApprovalResult.APPROVED

    @pytest.mark.asyncio
    async def test_approved_when_callback_returns_approved(self):
        async def approve_callback(action: str, user_id: str) -> ApprovalResult:
            await asyncio.sleep(0)
            return ApprovalResult.APPROVED

        guardian = Guardian(timeout_minutes=1, approval_callback=approve_callback)
        result = await guardian.request_approval("delete file", user_id="u1")
        assert result == ApprovalResult.APPROVED

    @pytest.mark.asyncio
    async def test_denied_when_callback_returns_denied(self):
        async def deny_callback(action: str, user_id: str) -> ApprovalResult:
            await asyncio.sleep(0)
            return ApprovalResult.DENIED

        guardian = Guardian(timeout_minutes=1, approval_callback=deny_callback)
        result = await guardian.request_approval("delete file", user_id="u1")
        assert result == ApprovalResult.DENIED

    @pytest.mark.asyncio
    async def test_timeout_when_callback_hangs(self):
        async def slow_callback(action: str, user_id: str) -> ApprovalResult:
            await asyncio.sleep(999)
            return ApprovalResult.APPROVED

        # 0 minutes = ~0 seconds timeout → effectively instant timeout
        guardian = Guardian(timeout_minutes=0, approval_callback=slow_callback)
        # We need a very small timeout. Set directly.
        guardian._timeout = 0.1
        result = await guardian.request_approval("delete file", user_id="u1")
        assert result == ApprovalResult.TIMED_OUT

    @pytest.mark.asyncio
    async def test_critical_requires_two_approvals(self):
        calls: list[str] = []

        async def approve_callback(action: str, user_id: str) -> ApprovalResult:
            await asyncio.sleep(0)
            calls.append(action)
            return ApprovalResult.APPROVED

        guardian = Guardian(timeout_minutes=1, approval_callback=approve_callback)
        result = await guardian.request_critical_approval("shutdown", user_id="u1")

        assert result == ApprovalResult.APPROVED
        assert len(calls) == 2
        assert calls[0].startswith("[CRITICAL-1/2]")
        assert calls[1].startswith("[CRITICAL-2/2]")
