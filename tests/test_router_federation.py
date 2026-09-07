"""Router federation and provider fallback tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.router import CognitiveRouter
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory
from memory.state import StateTracker
from models.messages import Message, MessageRole
from tools.registry import ToolRegistry


class _FailingGroqLLM:
    async def ainvoke(self, _messages):
        raise RuntimeError("429 rate limit from groq")


class _GeminiLLM:
    def __init__(self, content: str = '{"needs_plan": false, "steps": []}') -> None:
        self._content = content

    async def ainvoke(self, _messages):
        return SimpleNamespace(content=self._content)


@pytest.mark.asyncio
async def test_router_falls_back_from_groq_to_gemini_on_429(tmp_path):
    registry = ToolRegistry()
    short_term = ShortTermMemory(max_messages=10)
    long_term = LongTermMemory(persist_dir=str(tmp_path / "chroma"))

    state = StateTracker(tmp_path / "state.db")
    await state.initialize()

    router = CognitiveRouter(
        tool_registry=registry,
        short_term=short_term,
        long_term=long_term,
        state_tracker=state,
    )

    # Force runtime preference to groq first with gemini fallback.
    router._provider_sequence = ["groq", "gemini"]
    router._runtime_provider = "groq"
    router._llm = _FailingGroqLLM()

    def fake_switch(provider: str, *, reason: str = "runtime") -> bool:
        if provider == "gemini":
            router._runtime_provider = "gemini"
            router._llm = _GeminiLLM()
            return True
        return False

    router._switch_provider = fake_switch  # type: ignore[method-assign]
    router._can_rotate_groq_route = lambda: False  # type: ignore[method-assign]
    router._provider_has_credentials = lambda provider, settings=None: (
        provider
        in {
            "groq",
            "gemini",
        }
    )  # type: ignore[method-assign]

    message = Message(role=MessageRole.USER, content="Basit bir selam ver", user_id="u1")
    response = await router.handle_message(message, conversation_id="c1")

    assert isinstance(response, str)
    assert router._runtime_provider == "gemini"

    await router.shutdown()
    await state.close()
