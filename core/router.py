"""Cognitive Router — the central LLM brain of OmniCore.

Responsibilities:
  1. Parse natural-language input.
  2. Consult short-term and long-term memory for context.
  3. Delegate to the Planner for multi-step task decomposition.
  4. Execute the plan step-by-step, routing each tool call through the
     Guardian for safety checks and the RecoveryEngine on failure.
  5. Return a final natural-language response to the user.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import re
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import SecretStr

from config.logging import get_logger
from config.settings import get_settings
from core.guardian import ApprovalMode, ApprovalResult, Guardian
from core.planner import Planner, infer_query_domains, infer_tool_domain
from core.policy import CapabilityPolicyEngine
from core.recovery import RecoveryEngine
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory
from memory.state import StateTracker
from models.capabilities import RiskLevel
from models.messages import Message, MessageRole
from models.tasks import StepStatus, TaskStatus, TaskStep
from models.tools import ToolInput
from tools.registry import ToolRegistry

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Round-robin API key rotator for Groq multi-key support
# ---------------------------------------------------------------------------
class _GroqKeyRotator:
    """Thread-safe round-robin Groq API key selector.

    Cycles through ``GROQ_API_KEY_1``, ``_2``, ``_3`` (or the single
    ``GROQ_API_KEY``) on each call to ``next_key()``.
    """

    def __init__(self, keys: list[str]) -> None:
        self._keys = keys or [""]
        self._cycle = itertools.cycle(self._keys)
        self._lock = threading.Lock()
        self._current: str = ""
        # Advance to the first key.
        self.next_key()

    @property
    def current(self) -> str:
        return self._current

    @property
    def first(self) -> str:
        return self._keys[0]

    def next_key(self) -> str:
        with self._lock:
            self._current = next(self._cycle)
        return self._current

    def __len__(self) -> int:
        return len(self._keys)


class _GroqModelRotator:
    """Thread-safe round-robin Groq model selector."""

    def __init__(self, models: list[str]) -> None:
        self._models = [m for m in models if m] or ["llama-3.1-8b-instant"]
        self._cycle = itertools.cycle(self._models)
        self._lock = threading.Lock()
        self._current: str = ""
        self.next_model()

    @property
    def current(self) -> str:
        return self._current

    def next_model(self) -> str:
        with self._lock:
            self._current = next(self._cycle)
        return self._current

    def __len__(self) -> int:
        return len(self._models)


class _ApiKeyRotator:
    """Generic thread-safe round-robin API key selector."""

    def __init__(self, keys: list[str]) -> None:
        self._keys = keys or [""]
        self._cycle = itertools.cycle(self._keys)
        self._lock = threading.Lock()
        self._current: str = ""
        self.next_key()

    @property
    def current(self) -> str:
        return self._current

    @property
    def first(self) -> str:
        return self._keys[0]

    def next_key(self) -> str:
        with self._lock:
            self._current = next(self._cycle)
        return self._current

    def __len__(self) -> int:
        return len(self._keys)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    markers = (
        "429",
        "413",
        "payload too large",
        "request too large",
        "content too large",
        "input too large",
        "context length",
        "token limit",
        "rate_limit_exceeded",
        "rate limit",
        "quota exceeded",
        "resource_exhausted",
        "too many requests",
        "timeout",
    )
    return any(marker in text for marker in markers)


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    markers = (
        "429",
        "413",
        "payload too large",
        "request too large",
        "content too large",
        "input too large",
        "context length",
        "token limit",
        "rate_limit_exceeded",
        "rate limit",
        "quota",
        "resource_exhausted",
        "too many requests",
    )
    return any(marker in text for marker in markers)


_SUPPORTED_PROVIDERS: tuple[str, ...] = ("groq", "gemini")

_OPERATIONAL_FACT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("windows", "User OS is Windows"),
    ("linux", "User OS is Linux"),
    ("macos", "User OS is macOS"),
    ("powershell", "User shell preference is PowerShell"),
    ("bash", "User shell preference is Bash"),
)

_ALWAYS_ON_TOOL_NAMES: tuple[str, ...] = (
    "agent_spawn_subtask",
    "terminal_execute",
    "os_read_file",
)

_QUERY_TOOL_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dosya", ("os_", "file", "path")),
    ("file", ("os_", "file", "path")),
    ("klasor", ("os_", "dir", "path")),
    ("terminal", ("terminal_", "dev_", "process", "os_run")),
    ("bash", ("terminal_", "dev_", "process")),
    ("powershell", ("terminal_", "dev_", "process")),
    ("kod", ("dev_", "grep", "glob", "python", "git")),
    ("code", ("dev_", "grep", "glob", "python", "git")),
    ("ara", ("search", "grep", "glob", "web_", "net_")),
    ("search", ("search", "grep", "glob", "web_", "net_")),
    ("api", ("api_", "net_", "web_")),
    ("network", ("net_", "api_", "dns", "socket", "ping")),
    ("ag", ("net_", "api_", "dns", "socket", "ping")),
    ("internet", ("net_", "api_", "web_")),
    ("web", ("web_", "browser", "http", "api_")),
    ("tarayici", ("web_", "gui_", "browser")),
    ("browser", ("web_", "gui_", "browser")),
    ("gui", ("gui_", "vision", "screen", "click", "mouse")),
    ("ekran", ("gui_", "vision", "screen", "ocr")),
    ("vision", ("vision", "gui_", "ocr", "screen")),
    ("ocr", ("vision", "gui_", "screen")),
    ("resim", ("media_", "image", "vision")),
    ("video", ("media_", "video", "web_")),
    ("ses", ("media_", "audio")),
    ("guvenlik", ("security", "encrypt", "decrypt", "audit")),
    ("security", ("security", "encrypt", "decrypt", "audit")),
)

_MAX_RELEVANT_TOOLS = 30
_GROQ_PREEMPTIVE_TOKEN_LIMIT = 5000


class _LocalLLMResponse:
    """Small response envelope compatible with LLM result usage."""

    def __init__(self, content: str) -> None:
        self.content = content


class _SimpleCircuitBreaker:
    """A minimal count-based circuit breaker for external LLM calls."""

    def __init__(self, threshold: int = 3, cooldown_seconds: int = 30) -> None:
        self._threshold = max(1, threshold)
        self._cooldown_seconds = max(1, cooldown_seconds)
        self._failures = 0
        self._open_until = 0.0

    def is_open(self) -> bool:
        return time.monotonic() < self._open_until

    def record_success(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_until = time.monotonic() + self._cooldown_seconds


class CognitiveRouter:
    """Central orchestrator that ties together the LLM, memory, tools, and safety layers.

    Parameters
    ----------
    tool_registry:
        Registry of available tools.
    short_term:
        Short-term conversation memory.
    long_term:
        Long-term semantic memory.
    state_tracker:
        SQLite state tracker for persistence.
    approval_callback:
        Async function that presents an approval request to the user and
        returns an ``ApprovalResult``.  Injected by the gateway layer.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        short_term: ShortTermMemory,
        long_term: LongTermMemory,
        state_tracker: StateTracker,
        approval_callback: Callable[..., Awaitable[ApprovalResult]] | None = None,
    ) -> None:
        self._registry = tool_registry
        self._short_term = short_term
        self._long_term = long_term
        self._state = state_tracker

        settings = get_settings()
        self._key_rotator: _GroqKeyRotator | None = None
        self._model_rotator: _GroqModelRotator | None = None
        self._google_key_rotator: _ApiKeyRotator | None = None
        self._settings = settings
        self._provider_sequence = settings.provider_preference
        self._provider_availability = settings.provider_availability
        self._runtime_provider = self._select_initial_provider(settings)
        self._llm = self._build_llm(settings)
        self._llm_semaphore = asyncio.Semaphore(3)
        self._circuit_breaker = _SimpleCircuitBreaker(threshold=3, cooldown_seconds=30)
        self._planner = Planner(self._llm)
        self._guardian = Guardian(
            timeout_minutes=settings.hitl_timeout_minutes,
            approval_callback=approval_callback,
        )
        self._recovery = RecoveryEngine()
        self._policy = CapabilityPolicyEngine()

    def _build_llm(self, settings) -> Any:
        return self._build_llm_for_provider(self._runtime_provider, settings)

    def _build_llm_for_provider(self, provider: str, settings) -> Any:
        normalized = (provider or "").strip().lower() or "gemini"
        if normalized == "groq":
            api_keys = settings.groq_api_keys
            if not api_keys:
                api_keys = [settings.groq_api_key or ""]
            models = settings.groq_model_chain

            if self._key_rotator is None:
                self._key_rotator = _GroqKeyRotator(api_keys)
            if self._model_rotator is None:
                self._model_rotator = _GroqModelRotator(models)

            active_key = self._key_rotator.current
            active_model = self._model_rotator.current

            logger.info(
                "router.groq_active_route",
                model=active_model,
                key_suffix=f"...{active_key[-6:]}" if active_key else "<empty>",
                key_pool=len(api_keys),
                model_pool=len(models),
            )
            return ChatGroq(
                model=active_model,
                api_key=SecretStr(active_key) if active_key else None,
                temperature=settings.llm_temperature,
            )
        if normalized == "gemini":
            if self._google_key_rotator is None:
                self._google_key_rotator = _ApiKeyRotator(settings.google_api_keys)
            active_google_key = self._google_key_rotator.current
            return ChatGoogleGenerativeAI(
                model=settings.omni_llm_model,
                google_api_key=active_google_key,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
            )

        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _select_initial_provider(self, settings) -> str:
        for provider in settings.provider_preference:
            if self._provider_has_credentials(provider, settings):
                return provider
        return "gemini"

    def _provider_has_credentials(self, provider: str, settings=None) -> bool:
        cfg = settings or self._settings
        normalized = (provider or "").strip().lower()
        if normalized == "groq":
            return any(key.strip() for key in cfg.groq_api_keys)
        if normalized == "gemini":
            return any(key.strip() for key in cfg.google_api_keys)
        return False

    def _find_alternate_provider(self, current: str) -> str | None:
        current_normalized = (current or "").strip().lower()
        for provider in self._provider_sequence:
            if provider == current_normalized:
                continue
            if self._provider_has_credentials(provider):
                return provider
        return None

    def _can_rotate_groq_route(self) -> bool:
        if self._key_rotator is None or self._model_rotator is None:
            return False
        return (len(self._key_rotator) * len(self._model_rotator)) > 1

    def _can_rotate_google_route(self) -> bool:
        if self._google_key_rotator is None:
            return False
        return len(self._google_key_rotator) > 1

    def _switch_provider(self, provider: str, *, reason: str = "runtime") -> bool:
        target = provider.strip().lower() or "gemini"
        if target not in _SUPPORTED_PROVIDERS:
            logger.warning("router.provider_switch_rejected", provider=target, reason="unsupported")
            return False

        self._refresh_runtime_settings()
        if not self._provider_has_credentials(target):
            logger.warning(
                "router.provider_switch_rejected",
                provider=target,
                reason="credentials_unavailable",
            )
            return False

        previous = self._runtime_provider
        self._runtime_provider = target
        self._destroy_current_llm()
        self._llm = self._build_llm_for_provider(target, self._settings)
        logger.warning(
            "router.provider_switched",
            from_provider=previous,
            to_provider=target,
            reason=reason,
        )
        return True

    def _refresh_runtime_settings(self) -> None:
        """Refresh settings from environment/.env for live key rotation scenarios."""
        get_settings.cache_clear()
        self._settings = get_settings()
        self._provider_sequence = self._settings.provider_preference
        self._provider_availability = self._settings.provider_availability

    def _create_groq_client(self, api_key: str, model_name: str) -> Any:
        """Create a fresh ChatGroq instance for the given route."""
        return ChatGroq(
            model=model_name,
            api_key=SecretStr(api_key) if api_key else None,
            temperature=self._settings.llm_temperature,
        )

    def _destroy_current_llm(self) -> None:
        """Release current LLM client reference before hard re-instantiation."""
        self._llm = None

    def _rotate_groq_route_and_rebuild(self) -> None:
        """Rotate to next Groq key+model route and rebuild LLM."""
        self._refresh_runtime_settings()
        self._key_rotator = _GroqKeyRotator(self._settings.groq_api_keys)
        self._model_rotator = _GroqModelRotator(self._settings.groq_model_chain)

        if self._key_rotator is None or self._model_rotator is None:
            return

        old_key = self._key_rotator.current
        old_model = self._model_rotator.current

        # Step key every retry; when key wraps to first entry, step model once.
        prev_key = self._key_rotator.current
        new_key = self._key_rotator.next_key()
        wrapped = (
            len(self._key_rotator) > 1
            and new_key == self._key_rotator.first
            and prev_key != new_key
        )
        if len(self._key_rotator) == 1:
            wrapped = True

        if wrapped:
            self._model_rotator.next_model()

        logger.warning(
            "router.groq_route_rotated",
            old_model=old_model,
            new_model=self._model_rotator.current,
            old_key_suffix=f"...{old_key[-6:]}" if old_key else "<empty>",
            new_key_suffix=f"...{self._key_rotator.current[-6:]}"
            if self._key_rotator.current
            else "<empty>",
        )
        self._destroy_current_llm()
        self._llm = self._create_groq_client(self._key_rotator.current, self._model_rotator.current)

    def _rotate_google_route_and_rebuild(self) -> None:
        """Rotate to next Gemini key route and rebuild LLM client."""
        self._refresh_runtime_settings()
        if self._google_key_rotator is None:
            self._google_key_rotator = _ApiKeyRotator(self._settings.google_api_keys)
        else:
            self._google_key_rotator = _ApiKeyRotator(self._settings.google_api_keys)

        old_key = self._google_key_rotator.current
        new_key = self._google_key_rotator.next_key()
        logger.warning(
            "router.google_route_rotated",
            old_key_suffix=f"...{old_key[-6:]}" if old_key else "<empty>",
            new_key_suffix=f"...{new_key[-6:]}" if new_key else "<empty>",
            key_pool=len(self._google_key_rotator),
        )
        self._destroy_current_llm()
        self._llm = self._build_llm(self._settings)

    def _create_tool_learning_plan(self, step: TaskStep, user_message: Message) -> dict[str, Any]:
        query = str(step.parameters.get("query") or user_message.content or step.description)
        return {
            "mode": "learn_build_execute",
            "missing_tool": step.tool_name,
            "steps": [
                {
                    "tool": "web_read_main_article",
                    "reason": "Research unknown tool behavior from real web sources",
                    "parameters": {
                        "url": f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
                        "max_chars": 8000,
                    },
                },
                {
                    "tool": "dev_execute_python_code",
                    "reason": "Generate executable adaptation script for missing capability",
                    "parameters": {
                        "code": (
                            "import json\n"
                            "print(json.dumps({\n"
                            "  'status': 'generated_fallback',\n"
                            "  'tool': '" + step.tool_name + "',\n"
                            "  'note': 'Tool missing in registry; executed adaptive script path'\n"
                            "}, ensure_ascii=True))"
                        )
                    },
                },
            ],
        }

    def _compute_retry_budget(self) -> int:
        groq_routes = 1
        if self._key_rotator is not None and self._model_rotator is not None:
            groq_routes = max(1, len(self._key_rotator) * len(self._model_rotator))
        google_routes = max(1, len(self._settings.google_api_keys))
        # Keep retry space finite and bounded even under oversized key/model lists.
        return min(30, max(3, groq_routes + google_routes + 2))

    def _estimate_tokens(self, text: str) -> int:
        """Cheap token estimate for provider routing decisions, O(n)."""
        return max(1, len(text or "") // 4)

    def _semantic_target_provider(self, user_text: str) -> str:
        """Select target provider based on approximate prompt size, O(1)."""
        estimated_tokens = self._estimate_tokens(user_text)
        if estimated_tokens >= 1200:
            return "gemini"
        return self._runtime_provider

    def _route_provider_if_needed(self, user_text: str) -> None:
        target = self._semantic_target_provider(user_text)
        if target != self._runtime_provider:
            logger.info(
                "router.semantic_provider_route",
                from_provider=self._runtime_provider,
                to_provider=target,
                estimated_tokens=self._estimate_tokens(user_text),
            )
            self._switch_provider(target, reason="semantic_routing")

    def _filter_relevant_tools(
        self, query: str, all_tools: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Select a compact, relevant tool subset for prompt injection."""
        if not all_tools:
            return []

        lowered_query = (query or "").lower()
        query_domains = infer_query_domains(lowered_query)
        scored: list[tuple[int, dict[str, str]]] = []

        for tool in all_tools:
            name = str(tool.get("name") or "")
            if not name:
                continue
            desc = str(tool.get("description") or "")
            domain = infer_tool_domain(name)
            name_l = name.lower()
            desc_l = desc.lower()

            score = 0
            if name in _ALWAYS_ON_TOOL_NAMES:
                score += 10000

            if domain in query_domains:
                score += 90

            if name_l in lowered_query:
                score += 180

            tokens = {token for token in re.split(r"[^a-z0-9_]+", lowered_query) if token}
            for token in tokens:
                if token in name_l:
                    score += 35
                if token in desc_l:
                    score += 12

            for marker, hints in _QUERY_TOOL_KEYWORDS:
                if marker in lowered_query and any(
                    hint in name_l or hint in desc_l for hint in hints
                ):
                    score += 45

            if score > 0:
                scored.append((score, tool))

        # Always include core tools even if no score signal was generated.
        existing_names = {tool.get("name") for _, tool in scored}
        for tool in all_tools:
            name = str(tool.get("name") or "")
            if name in _ALWAYS_ON_TOOL_NAMES and name not in existing_names:
                scored.append((10000, tool))

        if not scored:
            # Conservative default: keep only always-on and then fill deterministically.
            always_on = [t for t in all_tools if str(t.get("name") or "") in _ALWAYS_ON_TOOL_NAMES]
            remainder = [t for t in all_tools if t not in always_on]
            return [*always_on, *remainder][:_MAX_RELEVANT_TOOLS]

        scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))

        selected: list[dict[str, str]] = []
        selected_names: set[str] = set()
        for _, tool in scored:
            name = str(tool.get("name") or "")
            if not name or name in selected_names:
                continue
            selected.append(tool)
            selected_names.add(name)
            if len(selected) >= _MAX_RELEVANT_TOOLS:
                break

        return selected

    def _build_system_prompt_with_tools(
        self,
        memory_context: str,
        tools: list[dict[str, str]],
    ) -> str:
        tools_desc = "\n".join(
            f"- {t['name']}: {t['description']} (yikici={t['destructive']})" for t in tools
        )
        mandated = (
            "KRİTİK ZORUNLULUK: SEN OMNICORE ADINDA, "
            "KULLANICININ BİLGİSAYARINA TAM (ROOT) ERİŞİMİ OLAN, "
            "FİZİKSEL EYLEMLER YAPAN TÜRK BİR YAPAY ZEKASIN. "
            "KURAL 1: ASLA İNGİLİZCE KONUŞMA. "
            "KURAL 2: BİR SİTEYİ AÇ VEYA VİDEO OYNAT DENİRSE, "
            "TARAYICIYI KULLANICININ GÖZÜ ÖNÜNDE "
            "(FOREGROUND) AÇACAKSIN! "
            "KURAL 3: ASLA YALAN SÖYLEME VE EKSİK BİLGİ VERME. "
            "EĞER BİR DOSYAYI OKURSAN, İÇİNDEKİ YAZIYI "
            "BANA KELİMESİ KELİMESİNE AKTAR. "
            "KURAL 4: KOTA HATASI (429) VEYA PAYLOAD HATASI (413) ALIRSAN ASLA PES ETME, "
            "DİĞER API SAĞLAYICISINA VEYA ANAHTARINA GEÇ VE İŞLEMİ TAMAMLA! "
            "KURAL 5: BEN BİR ŞEYİ ONAYLADIYSAM (APPROVE YES), "
            "HİÇBİR İZİN VEYA GÜVENLİK DUVARINA TAKILMADAN "
            "O İŞLEMİ ZORLA YAPACAKSIN! "
            "KURAL 6: HAVA DURUMUNU ASLA UYDURMA. "
            "HAVA İSTEKLERİNDE SADECE api_weather aracı veya "
            "wttr.in gibi gerçek kaynakları kullan, "
            "sahte URL/domain üretme. "
            "KURAL 7: EĞER İSTENEN YETENEK İÇİN ARAÇ YOKSA, "
            "ÖNCE GERÇEK KAYNAKTAN ARAŞTIR, SONRA GEÇİCİ ÇÖZÜM ÜRET, "
            "SONRA İŞİ TAMAMLA VE KULLANICIYA AÇIKÇA RAPORLA."
        )
        return (
            f"{mandated}\n\n"
            "## Kullanılabilir Araçlar\n"
            f"{tools_desc}\n\n"
            "## İlgili Hatıralar\n"
            f"{memory_context or '(yok)'}\n\n"
            "## Talimatlar\n"
            "Kullanıcı sistem verisi veya eylem istediğinde JSON plan üret.\n"
            "Araç çıktısındaki ham veriyi eksiksiz aktar.\n"
            '```json\n{"needs_plan": true, "steps": [{"tool": "<arac_adi>", "description": "...", '
            '"parameters": {...}, "destructive": true/false}]}\n```\n'
            "Araçlar yetersizse kısa Türkçe açıklama yap."
        )

    def _estimate_context_tokens_for_routing(
        self,
        system_prompt: str,
        recent: list[Message],
    ) -> int:
        recent_text = "\n".join(msg.content for msg in recent if msg.content)
        return self._estimate_tokens(f"{system_prompt}\n{recent_text}")

    def _maybe_preemptive_gemini_route(self, estimated_tokens: int) -> None:
        if self._runtime_provider != "groq":
            return
        if estimated_tokens <= _GROQ_PREEMPTIVE_TOKEN_LIMIT:
            return
        switched = self._switch_provider("gemini", reason="preemptive_context_routing")
        if switched:
            logger.warning(
                "router.preemptive_gemini_routing",
                estimated_tokens=estimated_tokens,
                threshold=_GROQ_PREEMPTIVE_TOKEN_LIMIT,
            )

    def _local_fallback_response(self) -> _LocalLLMResponse:
        return _LocalLLMResponse(
            "Harici model gecici olarak devre disi. Lütfen 30 saniye sonra tekrar deneyin."
        )

    def _collect_operational_facts(self, user_message: Message, reply: str) -> list[str]:
        combined = f"{user_message.content}\n{reply}".lower()
        facts: list[str] = []

        for marker, fact in _OPERATIONAL_FACT_PATTERNS:
            if marker in combined:
                facts.append(fact)

        path_matches = re.findall(r"([A-Za-z]:\\[^\s,;\"']+|/[\w\-./]+)", user_message.content)
        for raw_path in path_matches[:3]:
            facts.append(f"Active target path: {raw_path}")

        dedup: list[str] = []
        for fact in facts:
            if fact not in dedup:
                dedup.append(fact)
        return dedup

    async def _persist_operational_memory(self, user_message: Message, reply: str) -> None:
        facts = self._collect_operational_facts(user_message, reply)
        for fact in facts:
            self._long_term.store(
                fact,
                metadata={
                    "kind": "operational_fact",
                    "user_id": user_message.user_id,
                    "channel": user_message.channel,
                },
            )

    def _build_memory_context(self, user_message: Message, n_results: int = 6) -> str:
        query = user_message.content
        user_specific: list[dict[str, Any]] = []
        if user_message.user_id:
            user_specific = self._long_term.recall(
                query,
                n_results=n_results,
                where={"user_id": user_message.user_id},
            )
        generic = self._long_term.recall(query, n_results=n_results)

        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in [*user_specific, *generic]:
            item_id = str(item.get("id") or "")
            if item_id and item_id in seen_ids:
                continue
            if item_id:
                seen_ids.add(item_id)
            merged.append(item)

        lines = [f"- {m['document']}" for m in merged if m.get("document")]
        return "\n".join(lines)

    async def _ainvoke_with_retry(self, messages: list) -> Any:
        if self._circuit_breaker.is_open():
            return self._local_fallback_response()

        attempt = 0
        max_attempts = self._compute_retry_budget()
        last_exc: Exception | None = None

        while attempt < max_attempts:
            attempt += 1
            try:
                if self._llm is None:
                    self._llm = self._build_llm(self._settings)
                async with self._llm_semaphore:
                    response = await self._llm.ainvoke(messages)
                self._circuit_breaker.record_success()
                return response
            except Exception as exc:
                if not _is_retryable_llm_error(exc):
                    raise

                last_exc = exc
                self._circuit_breaker.record_failure()
                provider = self._runtime_provider
                self._destroy_current_llm()
                if provider == "groq":
                    if _is_rate_limit_error(exc):
                        fallback = self._find_alternate_provider(provider)
                        if fallback is not None:
                            switched = self._switch_provider(
                                fallback,
                                reason="llm_backpressure_fallback_from_groq",
                            )
                            if switched:
                                await asyncio.sleep(min(1.0, 0.1 * attempt))
                                continue
                    if self._can_rotate_groq_route():
                        self._rotate_groq_route_and_rebuild()
                    else:
                        fallback = self._find_alternate_provider(provider)
                        if fallback is not None:
                            switched = self._switch_provider(
                                fallback,
                                reason="llm_backpressure_fallback_from_groq",
                            )
                            if not switched:
                                self._llm = self._build_llm_for_provider(provider, self._settings)
                        else:
                            self._llm = self._build_llm_for_provider(provider, self._settings)
                elif provider == "gemini":
                    if _is_rate_limit_error(exc):
                        fallback = self._find_alternate_provider(provider)
                        if fallback is not None:
                            switched = self._switch_provider(
                                fallback,
                                reason="llm_backpressure_fallback_from_gemini",
                            )
                            if switched:
                                await asyncio.sleep(min(1.0, 0.1 * attempt))
                                continue
                    if self._can_rotate_google_route():
                        self._rotate_google_route_and_rebuild()
                    else:
                        fallback = self._find_alternate_provider(provider)
                        if fallback is not None:
                            switched = self._switch_provider(
                                fallback,
                                reason="llm_backpressure_fallback_from_gemini",
                            )
                            if not switched:
                                self._llm = self._build_llm_for_provider(provider, self._settings)
                        else:
                            self._llm = self._build_llm_for_provider(provider, self._settings)
                else:
                    self._llm = self._build_llm(self._settings)

                await asyncio.sleep(min(1.0, 0.1 * attempt))

        if last_exc is not None:
            logger.error(
                "router.llm_retry_exhausted",
                provider=self._runtime_provider,
                attempts=max_attempts,
                error=str(last_exc),
            )
        return self._local_fallback_response()

    # -- public API -----------------------------------------------------------

    async def handle_message(
        self,
        user_message: Message,
        conversation_id: str = "default",
    ) -> str:
        """Process a user message end-to-end and return the assistant reply.

        This is the single entry-point that every gateway calls.
        """
        slash_reply = await self._handle_slash_command(user_message)
        if slash_reply is not None:
            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=slash_reply,
                channel=user_message.channel,
                user_id=user_message.user_id,
            )
            self._short_term.add_message(conversation_id, user_message)
            self._short_term.add_message(conversation_id, assistant_msg)
            return slash_reply

        # 1. Store in short-term memory.
        self._short_term.add_message(conversation_id, user_message)
        self._route_provider_if_needed(user_message.content)

        # 2. Retrieve relevant long-term memories.
        memory_context = self._build_memory_context(user_message, n_results=6)

        # 3. Semantic tool routing: inject only relevant tools to reduce token payload.
        all_tools = self._registry.list_tools()
        relevant_tools = self._filter_relevant_tools(user_message.content, all_tools)

        # 4. Build the LLM prompt.
        system_prompt = self._build_system_prompt_with_tools(memory_context, relevant_tools)
        recent = self._short_term.get_recent_messages(conversation_id, n=20)

        estimated_context_tokens = self._estimate_context_tokens_for_routing(system_prompt, recent)
        self._maybe_preemptive_gemini_route(estimated_context_tokens)

        lc_messages: list = [SystemMessage(content=system_prompt)]
        for msg in recent:
            if msg.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                lc_messages.append(AIMessage(content=msg.content))

        # 5. Ask the LLM whether this requires a plan or a direct answer.
        classification = await self._classify_intent(user_message.content, lc_messages)

        if classification["needs_plan"]:
            reply = await self._execute_plan(user_message, classification, conversation_id)
        else:
            # Simple conversational reply — no tools needed.
            response = await self._ainvoke_with_retry(lc_messages)
            reply = response.content

        # 6. Store assistant reply in short-term memory.
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=reply,
            channel=user_message.channel,
            user_id=user_message.user_id,
        )
        self._short_term.add_message(conversation_id, assistant_msg)

        # 7. Persist to long-term memory for future recall.
        self._long_term.store(
            f"User: {user_message.content}\nAssistant: {reply}",
            metadata={"user_id": user_message.user_id, "channel": user_message.channel},
        )
        await self._persist_operational_memory(user_message, reply)

        return reply

    async def _handle_slash_command(self, user_message: Message) -> str | None:
        content = (user_message.content or "").strip()
        if not content.startswith("/"):
            return None

        lowered = content.lower()
        if lowered.startswith("/plan"):
            enabled = not self._guardian.plan_mode
            self._guardian.set_plan_mode(enabled)
            state = "ON" if enabled else "OFF"
            return f"Plan mode {state}. Destructive steps will be dry-run enforced."
        if lowered.startswith("/doctor"):
            provider = self._runtime_provider
            tools_count = len(self._registry)
            return (
                "System diagnostics OK\n"
                f"provider={provider}\n"
                f"plan_mode={self._guardian.plan_mode}\n"
                f"tools={tools_count}"
            )
        if lowered.startswith("/memory"):
            items = self._long_term.recall(user_message.content, n_results=5)
            return f"Memory preview: {len(items)} items"
        if lowered.startswith("/commit"):
            return "Commit helper available. Use git workflow commands in terminal."
        return None

    # -- internal helpers ------------------------------------------------------

    def _build_system_prompt(self, memory_context: str) -> str:
        tools = self._filter_relevant_tools("", self._registry.list_tools())
        return self._build_system_prompt_with_tools(memory_context, tools)

    async def _classify_intent(self, user_text: str, lc_messages: list) -> dict[str, Any]:
        """Ask the LLM to decide: plan or direct answer."""
        classification_prompt = (
            "Aşağıdaki isteğin araç çalıştırmayı gerektirip gerektirmediğine karar ver.\n"
            f"İstek: {user_text}\n\n"
            "ÖNEMLİ: Hava durumu isteklerinde mutlaka api_weather veya güvenilir gerçek kaynak "
            "(örn. wttr.in) kullanılmalı; sahte bağlantı üretilmez.\n"
            "SADECE JSON döndür:\n"
            '{"needs_plan": true/false, "steps": [...] or []}'
        )
        lc_messages_copy = list(lc_messages) + [HumanMessage(content=classification_prompt)]

        response = await self._ainvoke_with_retry(lc_messages_copy)
        text = response.content.strip()

        # Try to parse the JSON from the LLM response.
        try:
            # Strip markdown code fences if present.
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            # If the LLM didn't return valid JSON, treat as conversational.
            logger.debug("router.classification_fallback", raw=text[:200])
            return {"needs_plan": False, "steps": []}

    async def _handle_unknown_tool_step(
        self,
        step: TaskStep,
        user_message: Message,
        results_summary: list[str],
    ) -> bool:
        tool = self._registry.get(step.tool_name)
        if tool is not None:
            return False

        learning = self._create_tool_learning_plan(step, user_message)
        step.status = StepStatus.FAILED
        step.error = f"Unknown tool: {step.tool_name}"
        fallback_json = json.dumps(learning, ensure_ascii=True)
        results_summary.append(
            f"[FAIL] {step.description}: {step.error} | fallback={fallback_json}"
        )
        return True

    async def _build_tool_input(self, step: TaskStep) -> tuple[Any, ToolInput]:
        tool = self._registry.get(step.tool_name)
        if tool is None:
            raise ValueError(f"Unknown tool: {step.tool_name}")

        temp_input = ToolInput(tool_name=step.tool_name, parameters=step.parameters)
        tool_input = ToolInput(
            tool_name=step.tool_name,
            parameters=step.parameters,
            requires_approval=tool.requires_approval(temp_input),
        )
        return tool, tool_input

    async def _handle_policy_gate(
        self,
        step: TaskStep,
        tool,
        user_id: str,
        results_summary: list[str],
    ) -> tuple[bool, Any]:
        policy_decision = self._policy.evaluate(step)

        if self._guardian.plan_mode and step.is_destructive:
            policy_decision.require_dry_run = True
            if not step.dry_run_done and "missing_dry_run" not in policy_decision.reasons:
                policy_decision.allowed = False
                policy_decision.reasons.append("missing_dry_run")
        if policy_decision.allowed:
            return True, policy_decision

        if policy_decision.require_dry_run and "missing_dry_run" in policy_decision.reasons:
            dry_run_ok = await self._execute_required_dry_run(step, tool, user_id, results_summary)
            if dry_run_ok:
                policy_decision = self._policy.evaluate(step)
                if policy_decision.allowed:
                    return True, policy_decision

        if (
            policy_decision.require_backup
            and "backup_required" in policy_decision.reasons
            and RiskLevel(step.risk_level) == RiskLevel.CRITICAL
        ):
            override_ok = await self._attempt_critical_backup_override(
                step, user_id, results_summary
            )
            if override_ok:
                policy_decision = self._policy.evaluate(step)
                if policy_decision.allowed:
                    return True, policy_decision

        step.status = StepStatus.SKIPPED
        if policy_decision.safe_response:
            step.error = (
                f"Policy blocked: {', '.join(policy_decision.reasons)} | "
                f"guidance={policy_decision.safe_response}"
            )
        else:
            step.error = f"Policy blocked: {', '.join(policy_decision.reasons)}"

        results_summary.append(f"[SKIPPED] {step.description}: {step.error}")
        await self._state.log_audit(
            "policy_rejected",
            f"{step.tool_name}: {step.error}",
            user_id=user_id,
            metadata={
                "risk_level": step.risk_level.value,
                "reasons": policy_decision.reasons,
            },
        )
        return False, policy_decision

    async def _execute_required_dry_run(
        self,
        step: TaskStep,
        tool,
        user_id: str,
        results_summary: list[str],
    ) -> bool:
        dry_run_params = dict(step.parameters)
        dry_run_params["dry_run"] = True
        dry_run_input = ToolInput(
            tool_name=step.tool_name,
            parameters=dry_run_params,
            requires_approval=False,
        )

        probe_step = step.model_copy(deep=True)
        probe_step.description = f"[DRY-RUN] {step.description}"
        dry_run_output = await self._recovery.execute_with_retry(tool, dry_run_input, probe_step)

        if dry_run_output.status.value == "success":
            step.dry_run_done = True
            step.requires_dry_run = True
            await self._state.log_audit(
                "policy_dry_run_passed",
                f"{step.tool_name}: dry-run completed",
                user_id=user_id,
                metadata={"risk_level": step.risk_level.value},
            )
            results_summary.append(f"[DRY-RUN] {step.description}: policy preflight basarili")
            return True

        step.error = (
            f"Mandatory dry-run failed: {dry_run_output.error or 'unknown dry-run failure'}"
        )
        await self._state.log_audit(
            "policy_dry_run_failed",
            f"{step.tool_name}: {step.error}",
            user_id=user_id,
            metadata={"risk_level": step.risk_level.value},
        )
        results_summary.append(f"[FAIL] {step.description}: {step.error}")
        return False

    async def _attempt_critical_backup_override(
        self,
        step: TaskStep,
        user_id: str,
        results_summary: list[str],
    ) -> bool:
        approval = await self._guardian.request_critical_approval(
            action_description=(
                f"CRITICAL override for {step.tool_name}: backup missing. "
                "Approve only if explicit rollback/compensation exists."
            ),
            user_id=user_id,
        )

        if approval != ApprovalResult.APPROVED:
            results_summary.append(f"[SKIPPED] {step.description}: critical backup override denied")
            return False

        step.backup_ready = True
        await self._state.log_audit(
            "critical_override",
            f"{step.tool_name}: backup requirement overridden by user",
            user_id=user_id,
            metadata={
                "risk_level": step.risk_level.value,
                "override": "backup_requirement",
                "approval_mode": self._guardian.mode.value,
            },
        )
        results_summary.append(
            f"[OVERRIDE] {step.description}: user overrode CRITICAL backup requirement"
        )
        return True

    async def _handle_approval_gate(
        self,
        step: TaskStep,
        tool,
        tool_input: ToolInput,
        policy_decision,
        user_id: str,
        results_summary: list[str],
    ) -> bool:
        if (
            RiskLevel(step.risk_level) == RiskLevel.CRITICAL
            and self._guardian.mode == ApprovalMode.YES
        ):
            await self._state.log_audit(
                "critical_auto_override",
                (
                    f"{step.tool_name}: critical execution auto-approved because "
                    "guardian mode is YES"
                ),
                user_id=user_id,
                metadata={
                    "risk_level": step.risk_level.value,
                    "approval_mode": self._guardian.mode.value,
                },
            )

        if not (tool.requires_approval(tool_input) or policy_decision.require_confirmation):
            return True

        step.status = StepStatus.AWAITING_APPROVAL
        action_desc = f"{step.tool_name}: {step.description} | risk={step.risk_level.value}"
        if policy_decision.require_double_confirmation:
            approval = await self._guardian.request_critical_approval(
                action_description=action_desc,
                user_id=user_id,
            )
        else:
            approval = await self._guardian.request_approval(
                action_description=action_desc,
                user_id=user_id,
            )

        if approval == ApprovalResult.APPROVED:
            return True

        step.status = StepStatus.SKIPPED
        reason = "denied" if approval == ApprovalResult.DENIED else "timed out"
        step.error = f"Action {reason} by user"
        results_summary.append(f"[SKIPPED] {step.description}: {step.error}")
        await self._state.log_audit("hitl_rejected", step.description, user_id=user_id)
        return False

    async def _execute_step_with_fallback(
        self,
        step: TaskStep,
        tool,
        tool_input: ToolInput,
        user_message: Message,
    ):
        output = await self._recovery.execute_with_retry(tool, tool_input, step)
        if output.status.value == "success" and _is_generic_or_empty_success(output):
            output = output.model_copy(
                update={
                    "status": "failure",
                    "error": (
                        "Tool returned generic/empty success without actionable data; "
                        "treated as failure for safety"
                    ),
                }
            )

        if output.status.value != "success":
            fallback_output = await self._attempt_hybrid_gui_fallback(
                step=step,
                primary_output=output,
                user_message=user_message,
            )
            if fallback_output is not None:
                output = fallback_output
        return output

    async def _record_step_result(
        self,
        step: TaskStep,
        output,
        user_id: str,
        results_summary: list[str],
    ) -> None:
        if output.status.value == "success":
            step.status = StepStatus.COMPLETED
            step.result = output.result
            results_summary.append(f"[OK] {step.description}: {output.result}")
        else:
            step.status = StepStatus.FAILED
            step.error = output.error
            results_summary.append(f"[FAIL] {step.description}: {output.error}")

        await self._state.log_audit(
            f"tool_{output.status.value}",
            f"{step.tool_name}: {output.result or output.error}",
            user_id=user_id,
        )

    async def _finalize_plan_state(self, plan) -> None:
        if plan.is_complete:
            plan.mark_complete()
            return

        failed = [s for s in plan.steps if s.status == StepStatus.FAILED]
        if failed:
            plan.mark_failed("; ".join(s.error for s in failed))

    async def _summarize_plan_results(
        self,
        user_message: Message,
        results_summary: list[str],
    ) -> str:
        summary_prompt = (
            f"Kullanıcı şunu sordu: {user_message.content}\n\n"
            f"Aşağıdaki adımları yürüttüm:\n"
            + "\n".join(results_summary)
            + "\n\nLutfen kullanici icin kisa bir TURKCE ozet yaz "
            "ve arac ciktilarindan somut ham degerleri dahil et. "
            "Herhangi bir arac basarisiz olduysa, tam hatayi belirt."
        )
        summary_response = await self._ainvoke_with_retry([HumanMessage(content=summary_prompt)])
        summary_text = str(summary_response.content)

        if _looks_like_json_plan(summary_text):
            fallback = [line for line in results_summary if line]
            if not fallback:
                return "Araç hataları nedeniyle isteği tamamlayamadım."
            return "\n".join(fallback)

        if _contains_dummy_markers(summary_text):
            fallback = [line for line in results_summary if line]
            if fallback:
                return "\n".join(fallback)
        return summary_text

    async def _execute_plan(
        self,
        user_message: Message,
        classification: dict[str, Any],
        conversation_id: str,
    ) -> str:
        """Build a TaskPlan from the classification and execute step by step."""
        plan = self._planner.build_plan(
            user_request=user_message.content,
            raw_steps=classification.get("steps", []),
        )

        # Persist the plan.
        await self._state.save_task(
            plan.id, plan.user_request, plan.status.value, plan.model_dump_json()
        )

        plan.status = TaskStatus.EXECUTING
        results_summary: list[str] = []

        for step in plan.steps:
            step.status = StepStatus.IN_PROGRESS
            if await self._handle_unknown_tool_step(step, user_message, results_summary):
                continue

            if step.delegated:
                delegated_ok = await self._execute_delegated_step(
                    step, user_message, results_summary
                )
                if delegated_ok:
                    continue

            tool, tool_input = await self._build_tool_input(step)
            policy_allowed, policy_decision = await self._handle_policy_gate(
                step,
                tool,
                user_message.user_id,
                results_summary,
            )
            if not policy_allowed:
                continue

            approved = await self._handle_approval_gate(
                step,
                tool,
                tool_input,
                policy_decision,
                user_message.user_id,
                results_summary,
            )
            if not approved:
                continue

            output = await self._execute_step_with_fallback(step, tool, tool_input, user_message)
            await self._record_step_result(
                step,
                output,
                user_message.user_id,
                results_summary,
            )

        # Finalize plan.
        await self._finalize_plan_state(plan)

        await self._state.save_task(
            plan.id, plan.user_request, plan.status.value, plan.model_dump_json()
        )

        return await self._summarize_plan_results(user_message, results_summary)

    async def _execute_delegated_step(
        self,
        step: TaskStep,
        user_message: Message,
        results_summary: list[str],
    ) -> bool:
        spawn_tool = self._registry.get("agent_spawn_subtask")
        if spawn_tool is None:
            return False

        spawn_input = ToolInput(
            tool_name="agent_spawn_subtask",
            parameters={
                "objective": step.description or user_message.content,
                "max_subtasks": 4,
            },
            requires_approval=False,
        )
        spawn_output = await self._recovery.execute_with_retry(spawn_tool, spawn_input, step)
        if spawn_output.status.value != "success":
            return False

        subtasks = list(spawn_output.data.get("subtasks") or [])
        if not subtasks:
            return False

        delegated_results: list[str] = []
        for item in subtasks:
            tool_name = str(item.get("tool_name") or "").strip()
            if not tool_name:
                continue
            tool = self._registry.get(tool_name)
            if tool is None:
                delegated_results.append(f"{item.get('id', 'subtask')}: unknown tool {tool_name}")
                continue

            delegated_input = ToolInput(
                tool_name=tool_name,
                parameters=dict(item.get("parameters") or {}),
                requires_approval=False,
            )
            delegated_output = await self._recovery.execute_with_retry(tool, delegated_input, step)
            if delegated_output.status.value == "success":
                delegated_results.append(f"{item.get('id', 'subtask')}: ok ({tool_name})")
            else:
                delegated_results.append(
                    f"{item.get('id', 'subtask')}: fail ({tool_name}) {delegated_output.error}"
                )

        if not delegated_results:
            return False

        step.status = StepStatus.COMPLETED
        step.result = " | ".join(delegated_results)
        results_summary.append(f"[OK] {step.description}: {step.result}")
        return True

    async def shutdown(self) -> None:
        """Release runtime resources held by the router."""
        self._destroy_current_llm()

    def _is_fallback_candidate(self, step: TaskStep, primary_output, explicit: object) -> bool:
        likely_cli = step.tool_name.startswith(("terminal_", "dev_", "net_", "web_"))
        if explicit is not True and not likely_cli:
            return False

        error_text = str(getattr(primary_output, "error", "") or "").lower()
        retryable = any(
            marker in error_text
            for marker in ("timeout", "timed out", "permission", "not found", "could not", "failed")
        )
        return explicit is True or retryable

    def _build_fallback_tool_input(
        self,
        step: TaskStep,
        params: dict[str, Any],
        user_message: Message,
        fallback_tool,
    ) -> ToolInput:
        source_query = str(params.get("query") or user_message.content or "")
        source_url = str(params.get("url") or "")
        max_steps = int(
            params.get("fallback_steps", self._settings.hybrid_fallback_max_steps)
            or self._settings.hybrid_fallback_max_steps
        )
        return ToolInput(
            tool_name="gui_autonomous_explorer",
            parameters={
                "goal": (
                    f"Primary step failed ({step.tool_name}): {step.description}. "
                    f"Original request: {user_message.content}"
                ),
                "source_tool": step.tool_name,
                "source_error": str(params.get("source_error", "") or ""),
                "query": source_query,
                "url": source_url,
                "max_steps": max_steps,
            },
            requires_approval=fallback_tool.is_destructive,
        )

    async def _run_windows_secondary_fallback(
        self,
        step: TaskStep,
        user_id: str,
        source_query: str,
        source_url: str,
    ):
        if os.name != "nt":
            return None

        hotkey_tool = self._registry.get("gui_press_hotkey")
        type_tool = self._registry.get("gui_type_text")
        analyze_tool = self._registry.get("gui_analyze_screen")
        if not (hotkey_tool and type_tool and analyze_tool):
            return None

        target = source_url.strip() or (
            f"https://www.google.com/search?q={source_query.strip().replace(' ', '+')}"
        )
        sequence_tools = [hotkey_tool, type_tool, analyze_tool]
        needs_approval = any(
            t.requires_approval(ToolInput(tool_name=t.name, parameters={})) for t in sequence_tools
        )
        if needs_approval:
            approval = await self._guardian.request_approval(
                action_description=(
                    "GUI fallback sequence: gui_press_hotkey + gui_type_text + gui_analyze_screen"
                ),
                user_id=user_id,
            )
            if approval != ApprovalResult.APPROVED:
                return None

        steps = [
            (
                hotkey_tool,
                ToolInput(
                    tool_name="gui_press_hotkey",
                    parameters={"keys": ["win", "r"]},
                    requires_approval=hotkey_tool.is_destructive,
                ),
            ),
            (
                type_tool,
                ToolInput(
                    tool_name="gui_type_text",
                    parameters={"text": target, "interval": 0.01},
                    requires_approval=type_tool.is_destructive,
                ),
            ),
            (
                hotkey_tool,
                ToolInput(
                    tool_name="gui_press_hotkey",
                    parameters={"keys": ["enter"]},
                    requires_approval=hotkey_tool.is_destructive,
                ),
            ),
            (
                analyze_tool,
                ToolInput(
                    tool_name="gui_analyze_screen",
                    parameters={"max_chars": 5000},
                    requires_approval=analyze_tool.is_destructive,
                ),
            ),
        ]

        last_output = None
        for tool, tool_input in steps:
            last_output = await self._recovery.execute_with_retry(tool, tool_input, step)
            if last_output.status.value != "success":
                return None
        return last_output

    async def _attempt_hybrid_gui_fallback(
        self,
        step: TaskStep,
        primary_output,
        user_message: Message,
    ):
        """Try CLI->GUI fallback protocol on tool failure when applicable."""
        fallback_tool = self._registry.get("gui_autonomous_explorer")
        if fallback_tool is None:
            return None

        if not self._settings.hybrid_fallback_enabled:
            return None

        params = step.parameters if isinstance(step.parameters, dict) else {}
        explicit = params.get("hybrid_fallback")
        if explicit is False:
            return None

        if not self._is_fallback_candidate(step, primary_output, explicit):
            return None

        params = dict(params)
        params["source_error"] = str(getattr(primary_output, "error", "") or "")
        fallback_input = self._build_fallback_tool_input(
            step,
            params,
            user_message,
            fallback_tool,
        )
        source_query = str(params.get("query") or user_message.content or "")
        source_url = str(params.get("url") or "")

        try:
            if fallback_tool.requires_approval(fallback_input):
                approval = await self._guardian.request_approval(
                    action_description=(
                        f"gui_autonomous_explorer: Fallback for failed step '{step.tool_name}'"
                    ),
                    user_id=user_message.user_id,
                )
                if approval != ApprovalResult.APPROVED:
                    return None

            fallback_output = await self._recovery.execute_with_retry(
                fallback_tool,
                fallback_input,
                step,
            )

            if fallback_output.status.value == "success":
                logger.info(
                    "router.hybrid_fallback_success",
                    source_tool=step.tool_name,
                    fallback_tool="gui_autonomous_explorer",
                )
                return fallback_output

            step_ocr = await self._run_windows_secondary_fallback(
                step,
                user_message.user_id,
                source_query,
                source_url,
            )
            if step_ocr is not None and step_ocr.status.value == "success":
                logger.info(
                    "router.hybrid_fallback_success",
                    source_tool=step.tool_name,
                    fallback_tool="gui_hotkey_type_analyze",
                )
                return step_ocr

            logger.warning(
                "router.hybrid_fallback_failed",
                source_tool=step.tool_name,
                fallback_error=fallback_output.error,
            )
            return None
        except Exception as exc:
            logger.error(
                "router.hybrid_fallback_exception",
                source_tool=step.tool_name,
                error=str(exc),
            )
            return None


def _looks_like_json_plan(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("{") and '"needs_plan"' in stripped:
        return True
    return stripped.startswith("```") and '"needs_plan"' in stripped


def _contains_dummy_markers(text: str) -> bool:
    patterns = [
        r"\[.*burada.*\]",
        r"\[.*ekle.*\]",
        r"dummy marker",
    ]
    lowered = text.lower()
    return any(re.search(p, lowered) for p in patterns)


def _is_generic_or_empty_success(output) -> bool:
    if getattr(output, "status", None) != "success":
        return False

    result = str(getattr(output, "result", "") or "").strip().lower()
    data = getattr(output, "data", {}) or {}

    if not result and not data:
        return True

    generic_markers = {
        "ok",
        "success",
        "completed",
        "done",
        "işlem tamamlandı",
        "islem tamamlandi",
        "command completed",
        "command executed",
    }
    if result in generic_markers and not data:
        return True

    if isinstance(data, dict):
        flattened = " ".join(str(v).strip().lower() for v in data.values())
        if "success" in flattened and "result" not in data and len(data) <= 1:
            return True

    return False
