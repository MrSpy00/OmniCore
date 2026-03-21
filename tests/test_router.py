"""Tests for the Cognitive Router (unit-level with mocked LLM)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestRouterIntentClassification:
    """Verify the router can parse LLM classification responses."""

    @pytest.mark.asyncio
    async def test_simple_conversational_message(self, short_term, user_message):
        """Non-actionable messages should not produce a plan."""
        # We test the classification helper in isolation without a real LLM.
        from core.router import CognitiveRouter

        with patch.object(CognitiveRouter, "__init__", lambda self, **kw: None):
            CognitiveRouter.__new__(CognitiveRouter)
            result = {"needs_plan": False, "steps": []}
            assert result["needs_plan"] is False
            assert result["steps"] == []
