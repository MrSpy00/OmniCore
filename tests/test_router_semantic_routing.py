from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.router import CognitiveRouter, _is_rate_limit_error, _is_retryable_llm_error


class _Raising413LLM:
    async def ainvoke(self, _messages):
        raise RuntimeError("413 Payload Too Large")


def _minimal_router() -> CognitiveRouter:
    router = CognitiveRouter.__new__(CognitiveRouter)
    router._llm = None
    router._llm_semaphore = None
    router._circuit_breaker = SimpleNamespace(
        is_open=lambda: False,
        record_success=lambda: None,
        record_failure=lambda: None,
    )
    router._compute_retry_budget = lambda: 3  # type: ignore[method-assign]
    router._refresh_runtime_settings = lambda: None  # type: ignore[method-assign]
    router._destroy_current_llm = lambda: None  # type: ignore[method-assign]
    return router


def test_error_classifiers_include_413_and_token_backpressure():
    err = RuntimeError("413 Payload Too Large")
    assert _is_rate_limit_error(err) is True
    assert _is_retryable_llm_error(err) is True

    err2 = RuntimeError("rate_limit_exceeded: token limit exceeded")
    assert _is_rate_limit_error(err2) is True
    assert _is_retryable_llm_error(err2) is True


def test_filter_relevant_tools_caps_to_12_and_keeps_always_on():
    router = _minimal_router()
    tools = [
        {"name": f"dev_tool_{i}", "description": "developer utility", "destructive": "False"}
        for i in range(80)
    ]
    tools.extend(
        [
            {
                "name": "agent_spawn_subtask",
                "description": "spawn delegated subtasks",
                "destructive": "False",
            },
            {
                "name": "terminal_execute",
                "description": "execute shell commands",
                "destructive": "True",
            },
            {
                "name": "os_read_file",
                "description": "read file content",
                "destructive": "False",
            },
        ]
    )

    selected = router._filter_relevant_tools("kod ara grep TODO", tools)
    names = {t["name"] for t in selected}
    assert len(selected) <= 12
    assert "agent_spawn_subtask" in names
    assert "terminal_execute" in names
    assert "os_read_file" in names


def test_preemptive_route_switches_groq_to_gemini_when_large_context():
    router = _minimal_router()
    router._runtime_provider = "groq"
    switched: list[tuple[str, str]] = []

    def _switch(provider: str, *, reason: str = "runtime") -> bool:
        switched.append((provider, reason))
        router._runtime_provider = provider
        return True

    router._switch_provider = _switch  # type: ignore[method-assign]
    router._maybe_preemptive_gemini_route(estimated_tokens=5200)

    assert router._runtime_provider == "gemini"
    assert switched
    assert switched[0][0] == "gemini"


@pytest.mark.asyncio
async def test_ainvoke_with_retry_falls_back_to_gemini_on_413_error(monkeypatch):
    router = _minimal_router()
    router._runtime_provider = "groq"
    router._llm = _Raising413LLM()
    router._llm_semaphore = SimpleNamespace()

    class _NoopSemaphore:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    router._llm_semaphore = _NoopSemaphore()
    switch_calls: list[tuple[str, str]] = []

    class _GeminiLLM:
        async def ainvoke(self, _messages):
            return SimpleNamespace(content="ok")

    def _switch(provider: str, *, reason: str = "runtime") -> bool:
        if provider != "gemini":
            return False
        router._runtime_provider = "gemini"
        router._llm = _GeminiLLM()
        switch_calls.append((provider, reason))
        return True

    router._switch_provider = _switch  # type: ignore[method-assign]
    router._find_alternate_provider = lambda current: "gemini"  # type: ignore[method-assign]
    router._can_rotate_groq_route = lambda: False  # type: ignore[method-assign]
    router._can_rotate_google_route = lambda: False  # type: ignore[method-assign]
    router._build_llm_for_provider = lambda provider, settings: _GeminiLLM()  # type: ignore[method-assign]
    router._settings = SimpleNamespace(google_api_keys=["k"])

    async def _fast_sleep(_seconds: float):
        return None

    monkeypatch.setattr("core.router.asyncio.sleep", _fast_sleep)

    out = await router._ainvoke_with_retry([SimpleNamespace(content="x")])
    assert getattr(out, "content", "") == "ok"
    assert router._runtime_provider == "gemini"
    assert switch_calls
