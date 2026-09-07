"""Comprehensive tests for CognitiveRouter and internal routing components."""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from core.guardian import ApprovalMode, Guardian
from core.policy import PolicyDecision
from core.router import (
    CognitiveRouter,
    _ApiKeyRotator,
    _classify_llm_error,
    _GroqModelRotator,
    _is_rate_limit_error,
    _is_retryable_llm_error,
)
from models.capabilities import RiskLevel
from models.messages import Message, MessageRole
from models.tasks import StepStatus, TaskStep
from models.tools import ToolInput


class TestRotators:
    """Test API key and model rotators for thread-safety and cycling."""

    def test_api_key_rotator_basic(self):
        rotator = _ApiKeyRotator(["key1", "key2", "key3"])
        assert len(rotator) == 3
        assert rotator.first == "key1"
        assert rotator.current == "key1"
        assert rotator.next_key() == "key2"
        assert rotator.next_key() == "key3"
        assert rotator.next_key() == "key1"

    @pytest.mark.asyncio
    async def test_api_key_rotator_async(self):
        rotator = _ApiKeyRotator(["k1", "k2"])
        k = await rotator.get_next_key()
        assert k in ("k1", "k2")

    def test_api_key_rotator_empty(self):
        rotator = _ApiKeyRotator([])
        assert len(rotator) == 1
        assert rotator.first == ""
        assert rotator.current == ""
        assert rotator.next_key() == ""

    def test_api_key_rotator_concurrent_threads(self):
        keys = [f"key_{i}" for i in range(10)]
        rotator = _ApiKeyRotator(keys)
        results = []

        def worker():
            for _ in range(50):
                results.append(rotator.next_key())

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 250
        assert all(k.startswith("key_") for k in results)

    def test_groq_model_rotator_basic(self):
        rotator = _GroqModelRotator(["model-a", "model-b"])
        assert len(rotator) == 2
        assert rotator.current == "model-a"
        assert rotator.next_model() == "model-b"
        assert rotator.next_model() == "model-a"

    @pytest.mark.asyncio
    async def test_groq_model_rotator_async(self):
        rotator = _GroqModelRotator(["model-x", "model-y"])
        m = await rotator.get_next_model()
        assert m in ("model-x", "model-y")

    def test_groq_model_rotator_empty_fallback(self):
        rotator = _GroqModelRotator([])
        assert len(rotator) == 1
        assert rotator.current == "openai/gpt-oss-20b"


class TestErrorClassification:
    """Test retryable and rate-limit error markers."""

    def test_rate_limit_error(self):
        exc = Exception("HTTP 429 Too Many Requests: rate_limit_exceeded")
        retryable, rate_limit = _classify_llm_error(exc)
        assert retryable is True
        assert rate_limit is True
        assert _is_rate_limit_error(exc) is True
        assert _is_retryable_llm_error(exc) is True

    def test_retryable_timeout_error(self):
        exc = TimeoutError("Request timed out waiting for upstream LLM")
        retryable, rate_limit = _classify_llm_error(exc)
        assert retryable is True
        assert rate_limit is False
        assert _is_retryable_llm_error(exc) is True

    def test_token_limit_error(self):
        exc = Exception("Error: token limit reached for model context")
        retryable, rate_limit = _classify_llm_error(exc)
        assert retryable is True
        assert rate_limit is False

    def test_non_retryable_error(self):
        exc = ValueError("Invalid prompt parameters")
        retryable, rate_limit = _classify_llm_error(exc)
        assert retryable is False
        assert rate_limit is False
        assert _is_rate_limit_error(exc) is False
        assert _is_retryable_llm_error(exc) is False


class TestApprovalGate:
    """Test approval gate behavior under different Guardian modes and risk levels."""

    @pytest.fixture()
    def mock_router(self, state_tracker):
        router = object.__new__(CognitiveRouter)
        router._guardian = Guardian(ApprovalMode.ASK)
        router._state = state_tracker
        return router

    @pytest.mark.asyncio
    async def test_auto_approve_yes_mode_normal_risk(self, mock_router):
        mock_router._guardian.set_mode("yes")
        step = TaskStep(
            id="step-1",
            description="Read status",
            tool_name="os_read_file",
            parameters={},
            risk_level=RiskLevel.LOW,
        )
        tool = MagicMock()
        tool_input = ToolInput(tool_name="os_read_file", parameters={})
        decision = PolicyDecision(allowed=True)
        summary: list[str] = []

        approved = await mock_router._handle_approval_gate(
            step=step,
            tool=tool,
            tool_input=tool_input,
            policy_decision=decision,
            user_id="user1",
            results_summary=summary,
        )
        assert approved is True
        assert len(summary) == 0

    @pytest.mark.asyncio
    async def test_auto_approve_yes_mode_critical_risk(self, mock_router):
        mock_router._guardian.set_mode("yes")
        step = TaskStep(
            id="step-2",
            description="Format drive",
            tool_name="execute_shell",
            parameters={},
            risk_level=RiskLevel.CRITICAL,
        )
        tool = MagicMock()
        tool_input = ToolInput(tool_name="execute_shell", parameters={})
        decision = PolicyDecision(allowed=True)
        summary: list[str] = []

        approved = await mock_router._handle_approval_gate(
            step=step,
            tool=tool,
            tool_input=tool_input,
            policy_decision=decision,
            user_id="admin",
            results_summary=summary,
        )
        assert approved is True

    @pytest.mark.asyncio
    async def test_no_approval_needed_returns_true(self, mock_router):
        mock_router._guardian.set_mode("ask")
        step = TaskStep(
            id="step-3",
            description="Calculate time",
            tool_name="api_datetime",
            parameters={},
            risk_level=RiskLevel.LOW,
        )
        tool = MagicMock()
        tool.requires_approval.return_value = False
        tool_input = ToolInput(tool_name="api_datetime", parameters={})
        decision = PolicyDecision(allowed=True, require_confirmation=False)
        summary: list[str] = []

        approved = await mock_router._handle_approval_gate(
            step=step,
            tool=tool,
            tool_input=tool_input,
            policy_decision=decision,
            user_id="user1",
            results_summary=summary,
        )
        assert approved is True

    @pytest.mark.asyncio
    async def test_approval_denied_in_ask_mode(self, mock_router):
        mock_router._guardian.set_mode("ask")
        # Set callback returning False (denied)
        mock_router._guardian.set_approval_callback(lambda action, user: False)

        step = TaskStep(
            id="step-4",
            description="Delete system file",
            tool_name="os_delete_file",
            parameters={},
            risk_level=RiskLevel.HIGH,
        )
        tool = MagicMock()
        tool.requires_approval.return_value = True
        tool_input = ToolInput(tool_name="os_delete_file", parameters={})
        decision = PolicyDecision(allowed=True, require_confirmation=True)
        summary: list[str] = []

        approved = await mock_router._handle_approval_gate(
            step=step,
            tool=tool,
            tool_input=tool_input,
            policy_decision=decision,
            user_id="user1",
            results_summary=summary,
        )
        assert approved is False
        assert step.status == StepStatus.SKIPPED
        assert "denied" in step.error.lower()
        assert len(summary) == 1
        assert "[SKIPPED]" in summary[0]


class TestCognitiveRouterExecution:
    """Test full message routing through mocked CognitiveRouter."""

    @pytest.mark.asyncio
    async def test_conversational_response_flow(self, settings, short_term, state_tracker, tool_registry):
        mock_long_term = MagicMock()
        mock_long_term.recall.return_value = []
        mock_long_term.format_memory_for_prompt.return_value = ""

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=mock_long_term,
            state_tracker=state_tracker,
        )

        # Mock LLM to return non-plan conversational answer
        mock_chat = AsyncMock()
        mock_chat.ainvoke.return_value = AIMessage(content="OmniCore is operational and ready.")
        router._llm = mock_chat

        msg = Message(
            role=MessageRole.USER,
            content="What is your status?",
            channel="test",
            user_id="tester",
        )

        response = await router.handle_message(msg)
        assert isinstance(response, str)
        assert len(response) > 0
        assert "OmniCore" in response or "operational" in response

    @pytest.mark.asyncio
    async def test_tool_execution_flow(self, settings, short_term, state_tracker, tool_registry):
        mock_long_term = MagicMock()
        mock_long_term.recall.return_value = []
        mock_long_term.format_memory_for_prompt.return_value = ""

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=mock_long_term,
            state_tracker=state_tracker,
        )
        router._guardian.set_mode("yes")  # Auto-approve

        # Plan response from LLM
        plan_json = '{"plan": [{"tool": "api_datetime", "parameters": {}, "reason": "Check current time"}]}'
        mock_chat = AsyncMock()
        # First call is planner decomposition, second is final summary
        mock_chat.ainvoke.side_effect = [
            AIMessage(content=plan_json),
            AIMessage(content="The current UTC time is 2026-09-07T18:00:00Z."),
        ]
        router._llm = mock_chat

        msg = Message(
            role=MessageRole.USER,
            content="Check the current datetime",
            channel="test",
            user_id="tester",
        )

        response = await router.handle_message(msg)
        assert isinstance(response, str)
        assert len(response) > 0


class TestCircuitBreakerAndLocalResponse:
    """Test circuit breaker states and local fallback envelopes."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_trip_and_reset(self):
        from core.router import _SimpleCircuitBreaker

        cb = _SimpleCircuitBreaker(threshold=3, cooldown_seconds=60)
        assert cb.is_open() is False

        await cb.record_failure()
        assert cb.is_open() is False
        await cb.record_failure()
        assert cb.is_open() is False
        await cb.record_failure()
        assert cb.is_open() is True

        await cb.record_success()
        assert cb.is_open() is False

    @pytest.mark.asyncio
    async def test_local_llm_response(self):
        from core.router import _LocalLLMResponse

        resp = _LocalLLMResponse("Fallback response", is_fallback=True)
        assert resp.content == "Fallback response"
        assert resp.is_fallback is True
        result = await resp.ainvoke()
        assert result is resp


class TestProviderBuilding:
    """Test provider resolution and fallback when keys are missing."""

    def test_build_llm_for_provider_fallback_groq(self, tool_registry, short_term, state_tracker):
        from core.router import _LocalLLMResponse

        mock_settings = MagicMock()
        mock_settings.groq_api_keys = []
        mock_settings.groq_api_key = ""
        mock_settings.groq_model_chain = []
        mock_settings.llm_temperature = 0.7

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        llm = router._build_llm_for_provider("groq", mock_settings)
        assert isinstance(llm, _LocalLLMResponse)
        assert "not configured" in llm.content

    def test_build_llm_for_provider_fallback_gemini(self, tool_registry, short_term, state_tracker):
        from core.router import _ApiKeyRotator, _LocalLLMResponse

        mock_settings = MagicMock()
        mock_settings.google_api_keys = []
        mock_settings.google_api_key = ""
        mock_settings.llm_temperature = 0.7

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        router._google_key_rotator = _ApiKeyRotator([])
        llm = router._build_llm_for_provider("gemini", mock_settings)
        assert isinstance(llm, _LocalLLMResponse)
        assert "not configured" in llm.content

    def test_build_llm_for_provider_fallback_openai(self, tool_registry, short_term, state_tracker):
        from core.router import _LocalLLMResponse

        mock_settings = MagicMock()
        mock_settings.openai_api_key = ""
        mock_settings.llm_temperature = 0.7

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        llm = router._build_llm_for_provider("openai", mock_settings)
        assert isinstance(llm, _LocalLLMResponse)
        assert "not configured" in llm.content or "not installed" in llm.content

    def test_build_llm_for_provider_fallback_anthropic(self, tool_registry, short_term, state_tracker):
        from core.router import _LocalLLMResponse

        mock_settings = MagicMock()
        mock_settings.anthropic_api_key = ""
        mock_settings.llm_temperature = 0.7

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        llm = router._build_llm_for_provider("anthropic", mock_settings)
        assert isinstance(llm, _LocalLLMResponse)
        assert "not configured" in llm.content or "not installed" in llm.content

    def test_filter_relevant_tools_always_on(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        all_tools = [
            {"name": "check_datetime", "description": "Check current time", "destructive": "False"},
            {"name": "system_diagnostics", "description": "System health", "destructive": "False"},
            {"name": "unrelated_tool_xyz", "description": "Something random", "destructive": "False"},
        ]
        filtered = router._filter_relevant_tools("Check datetime please", all_tools)
        names = [t["name"] for t in filtered]
        assert "check_datetime" in names

    def test_filter_relevant_tools_media_query(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        all_tools = [
            {"name": "media_control_spotify_native", "description": "Control Spotify", "destructive": "False"},
            {"name": "gui_automation", "description": "Automate GUI clicks", "destructive": "True"},
        ]
        filtered = router._filter_relevant_tools("spotify muzik cal", all_tools)
        assert len(filtered) >= 1
        assert filtered[0]["name"] == "media_control_spotify_native"

    def test_hardware_adaptive_route_game_active(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        router._runtime_provider = "ollama"

        with (
            patch("core.vram_monitor.detect_running_games", return_value=["cs2.exe"]),
            patch.object(router, "_provider_has_credentials", return_value=True),
        ):
            target = router._power_and_hardware_adaptive_route()
            assert target in ("groq", "gemini")

    def test_hardware_adaptive_route_low_battery(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        router._runtime_provider = "ollama"
        mock_battery = MagicMock(power_plugged=False, percent=15)

        with (
            patch("core.vram_monitor.detect_running_games", return_value=[]),
            patch("psutil.sensors_battery", return_value=mock_battery),
            patch.object(router, "_provider_has_credentials", return_value=True),
        ):
            target = router._power_and_hardware_adaptive_route()
            assert target in ("groq", "gemini")

    @pytest.mark.asyncio
    async def test_build_system_prompt_with_tools(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        tools = [{"name": "mock_tool", "description": "does things", "destructive": "False"}]
        prompt = await router._build_system_prompt_with_tools("user loves python", tools)
        assert "mock_tool" in prompt
        assert "does things" in prompt

    def test_provider_credentials_check(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        mock_settings = MagicMock()
        mock_settings.groq_api_keys = ["gsk_123"]
        mock_settings.google_api_keys = []
        mock_settings.ollama_enabled = True

        assert router._provider_has_credentials("groq", mock_settings) is True
        assert router._provider_has_credentials("gemini", mock_settings) is False
        assert router._provider_has_credentials("ollama", mock_settings) is True

    def test_find_alternate_provider(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        router._provider_sequence = ["groq", "gemini", "ollama"]
        with patch.object(router, "_provider_has_credentials", side_effect=lambda p: p == "gemini"):
            alt = router._find_alternate_provider("groq")
            assert alt == "gemini"

    def test_can_rotate_routes(self, tool_registry, short_term, state_tracker):
        from core.router import _ApiKeyRotator, _GroqModelRotator

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        # Empty rotators
        assert router._can_rotate_groq_route() is False
        assert router._can_rotate_google_route() is False

        # Configured rotators
        router._key_rotator = _ApiKeyRotator(["k1", "k2"])
        router._model_rotator = _GroqModelRotator(["m1"])
        assert router._can_rotate_groq_route() is True

        router._google_key_rotator = _ApiKeyRotator(["gk1", "gk2"])
        assert router._can_rotate_google_route() is True

    def test_rotate_groq_route_and_rebuild(self, tool_registry, short_term, state_tracker):
        from core.router import _ApiKeyRotator, _GroqModelRotator

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        router._key_rotator = _ApiKeyRotator(["k1", "k2"])
        router._model_rotator = _GroqModelRotator(["m1", "m2"])

        with patch.object(router, "_create_groq_client", return_value=MagicMock()):
            router._rotate_groq_route_and_rebuild()
            assert router._key_rotator.current == "k2"

    def test_rotate_google_route_and_rebuild(self, tool_registry, short_term, state_tracker):
        from core.router import _ApiKeyRotator

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        router._google_key_rotator = _ApiKeyRotator(["gk1", "gk2"])

        with patch.object(router, "_build_llm_for_provider", return_value=MagicMock()):
            router._rotate_google_route_and_rebuild()
            assert router._google_key_rotator.current == "gk2"

    def test_switch_provider_unsupported(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        assert router._switch_provider("non_existent_provider") is False


class TestRouterSlashCommands:
    """Test CLI slash commands handled by CognitiveRouter."""

    @pytest.mark.asyncio
    async def test_slash_plan_toggle(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/plan", channel="cli", user_id="u1")
        resp1 = await router.handle_message(msg)
        assert "Plan mode ON" in resp1

        resp2 = await router.handle_message(msg)
        assert "Plan mode OFF" in resp2

    @pytest.mark.asyncio
    async def test_slash_doctor(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/doctor", channel="cli", user_id="u1")
        resp = await router.handle_message(msg)
        assert "OmniCore Sistem Teşhisi" in resp
        assert "Sağlayıcı:" in resp

    @pytest.mark.asyncio
    async def test_slash_memory_preview(self, tool_registry, short_term, state_tracker):
        mock_ltm = MagicMock()
        mock_ltm.recall.return_value = [{"document": "test doc"}]
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=mock_ltm,
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/memory python", channel="cli", user_id="u1")
        resp = await router.handle_message(msg)
        assert "Memory preview:" in resp

    @pytest.mark.asyncio
    async def test_slash_reset(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/reset", channel="cli", user_id="u1")
        resp = await router.handle_message(msg)
        assert "temizlendi" in resp

    @pytest.mark.asyncio
    async def test_slash_commit(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/commit", channel="cli", user_id="u1")
        resp = await router.handle_message(msg)
        assert "Commit helper available" in resp

    @pytest.mark.asyncio
    async def test_slash_models(self, tool_registry, short_term, state_tracker):
        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/models", channel="cli", user_id="u1")
        resp = await router.handle_message(msg)
        assert "Kullanılabilir LLM Modeller" in resp
        assert "GEMINI" in resp or "GROQ" in resp

    @pytest.mark.asyncio
    async def test_slash_taste(self, tool_registry, short_term, state_tracker):
        from memory.taste import get_taste_engine

        engine = get_taste_engine()
        engine.learn("language", "primary", "turkish")

        router = CognitiveRouter(
            tool_registry=tool_registry,
            short_term=short_term,
            long_term=MagicMock(),
            state_tracker=state_tracker,
        )
        msg = Message(role=MessageRole.USER, content="/taste", channel="cli", user_id="u1")
        resp = await router.handle_message(msg)
        assert "Öğrenilen Kullanıcı Tercihleri" in resp
        assert "turkish" in resp
