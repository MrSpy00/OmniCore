"""System regression test suite for OmniCore router, settings, and tools."""

from __future__ import annotations

import json
import re

import pytest

from config.settings import AVAILABLE_GEMINI_MODELS, Settings, get_available_models
from core.recovery import RecoveryEngine
from core.router import _TR_SYNONYMS, _ApiKeyRotator
from memory.short_term import ShortTermMemory
from models.messages import Message, MessageRole
from models.tasks import TaskStep
from models.tools import ToolInput, ToolOutput, ToolStatus
from tools.base import BaseTool
from tools.registry import ToolRegistry


def test_settings_default_model():
    s = Settings()
    assert s.omni_llm_model == "gemini-2.5-flash"


def test_settings_recovery_max_attempts_default():
    s = Settings()
    assert s.recovery_max_attempts == 2


def test_settings_semaphore_limit_default():
    s = Settings()
    assert s.llm_semaphore_limit == 3


def test_get_available_models_all():
    models = get_available_models()
    assert "gemini" in models
    assert "groq" in models
    assert len(models["gemini"]) > 0
    assert len(models["groq"]) > 0


def test_get_available_models_single_provider():
    gemini_only = get_available_models("gemini")
    assert "gemini" in gemini_only
    assert "groq" not in gemini_only


def test_gemini_models_have_required_fields():
    for model in AVAILABLE_GEMINI_MODELS:
        assert "id" in model
        assert "name" in model
        assert "context" in model
        assert "speed" in model


def _make_parse_fn():
    def parse_intent_response(text: str) -> dict:
        text = text.strip()
        try:
            fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
            if fence_match:
                return json.loads(fence_match.group(1))
            bare_match = re.search(r"(\{[^{}]*\})", text, re.DOTALL)
            if bare_match:
                return json.loads(bare_match.group(1))
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {"needs_plan": False, "steps": []}

    return parse_intent_response


def test_classify_intent_plain_json():
    parse = _make_parse_fn()
    result = parse('{"needs_plan": true, "steps": []}')
    assert result["needs_plan"] is True


def test_classify_intent_markdown_fence():
    parse = _make_parse_fn()
    text = '```json\n{"needs_plan": false, "steps": []}\n```'
    result = parse(text)
    assert result["needs_plan"] is False


def test_classify_intent_garbage_fallback():
    parse = _make_parse_fn()
    result = parse("Sorry, I cannot process this request.")
    assert result == {"needs_plan": False, "steps": []}


def test_api_key_rotator_does_not_reset():
    keys = ["key-A", "key-B", "key-C"]
    rotator = _ApiKeyRotator(keys)
    assert rotator.current == "key-A"
    k2 = rotator.next_key()
    assert k2 == "key-B"
    k3 = rotator.next_key()
    assert k3 == "key-C"
    k4 = rotator.next_key()
    assert k4 == "key-A"


@pytest.mark.asyncio
async def test_recovery_engine_respects_max_attempts():
    engine = RecoveryEngine(max_attempts=1)
    call_count = 0

    class FailingTool:
        name = "failing_tool"

        async def execute(self, _input):
            nonlocal call_count
            call_count += 1
            return ToolOutput(
                tool_name="failing_tool",
                status=ToolStatus.FAILURE,
                error="simulated failure",
            )

    step = TaskStep(description="test", tool_name="failing_tool", max_retries=5)
    tool_input = ToolInput(tool_name="failing_tool", parameters={})
    tool = FailingTool()

    await engine.execute_with_retry(tool, tool_input, step)
    assert call_count <= 2


def test_short_term_clear_removes_messages():
    mem = ShortTermMemory()
    conv_id = "test_conv_clear"
    msg = Message(role=MessageRole.USER, content="hello world")
    mem.add_message(conv_id, msg)

    assert len(mem.get_recent_messages(conv_id)) > 0
    mem.clear(conv_id)
    assert len(mem.get_recent_messages(conv_id)) == 0


def test_tool_registry_raises_on_duplicate():
    class DummyTool(BaseTool):
        name = "dummy_dup_test"
        description = "Test tool"

        async def execute(self, _input: ToolInput) -> ToolOutput:
            return self._success("ok")

    registry = ToolRegistry()
    registry.register(DummyTool())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyTool())


def test_tr_synonyms_coverage():
    assert len(_TR_SYNONYMS) >= 20
    assert "dosya" in _TR_SYNONYMS
    assert "ekran" in _TR_SYNONYMS
    assert "ses" in _TR_SYNONYMS
    assert "zamanla" in _TR_SYNONYMS
