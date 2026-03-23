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

import itertools
import json
import os
import re
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import SecretStr

from config.logging import get_logger
from config.settings import get_settings
from core.guardian import ApprovalResult, Guardian
from core.planner import Planner
from core.policy import CapabilityPolicyEngine
from core.recovery import RecoveryEngine
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory
from memory.state import StateTracker
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
        "rate limit",
        "quota exceeded",
        "resource_exhausted",
        "too many requests",
        "timeout",
    )
    return any(marker in text for marker in markers)


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
        self._runtime_provider = settings.llm_provider.strip().lower() or "gemini"
        self._settings = settings
        self._llm = self._build_llm(settings)
        self._planner = Planner(self._llm)
        self._guardian = Guardian(
            timeout_minutes=settings.hitl_timeout_minutes,
            approval_callback=approval_callback,
        )
        self._recovery = RecoveryEngine()
        self._policy = CapabilityPolicyEngine()

    def _build_llm(self, settings) -> Any:
        provider = self._runtime_provider
        if provider == "groq":
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
        if provider in ("", "gemini"):
            if self._google_key_rotator is None:
                self._google_key_rotator = _ApiKeyRotator(settings.google_api_keys)
            active_google_key = self._google_key_rotator.current
            return ChatGoogleGenerativeAI(
                model=settings.omni_llm_model,
                google_api_key=active_google_key,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
            )

        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

    def _switch_provider(self, provider: str) -> None:
        self._runtime_provider = provider.strip().lower() or "gemini"
        self._destroy_current_llm()
        self._llm = self._build_llm(self._settings)

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
        if self._google_key_rotator is None:
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

    async def _ainvoke_with_retry(self, messages: list) -> Any:
        attempt = 0
        max_attempts = self._compute_retry_budget()
        last_exc: Exception | None = None

        while attempt < max_attempts:
            attempt += 1
            try:
                if self._llm is None:
                    self._llm = self._build_llm(self._settings)
                return await self._llm.ainvoke(messages)
            except Exception as exc:
                if not _is_retryable_llm_error(exc):
                    raise

                last_exc = exc
                provider = self._runtime_provider
                self._destroy_current_llm()
                if provider == "groq":
                    exhausted_markers = (
                        "all configured groq",
                        "all keys",
                        "exhausted",
                        "quota",
                        "resource_exhausted",
                    )
                    detail = str(exc).lower()
                    single_route = (
                        self._key_rotator is not None
                        and self._model_rotator is not None
                        and len(self._key_rotator) <= 1
                        and len(self._model_rotator) <= 1
                    )
                    if single_route or any(marker in detail for marker in exhausted_markers):
                        logger.warning(
                            "router.provider_fallback",
                            from_provider="groq",
                            to_provider="gemini",
                            attempt=attempt,
                        )
                        self._switch_provider("gemini")
                    else:
                        self._rotate_groq_route_and_rebuild()
                elif provider in ("", "gemini"):
                    self._rotate_google_route_and_rebuild()
                else:
                    self._llm = self._build_llm(self._settings)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("LLM invocation failed")

    # -- public API -----------------------------------------------------------

    async def handle_message(
        self,
        user_message: Message,
        conversation_id: str = "default",
    ) -> str:
        """Process a user message end-to-end and return the assistant reply.

        This is the single entry-point that every gateway calls.
        """
        # 1. Store in short-term memory.
        self._short_term.add_message(conversation_id, user_message)

        # 2. Retrieve relevant long-term memories.
        memories = self._long_term.recall(user_message.content, n_results=3)
        memory_context = "\n".join(f"- {m['document']}" for m in memories if m.get("document"))

        # 3. Build the LLM prompt.
        system_prompt = self._build_system_prompt(memory_context)
        recent = self._short_term.get_recent_messages(conversation_id, n=20)
        lc_messages: list = [SystemMessage(content=system_prompt)]
        for msg in recent:
            if msg.role == MessageRole.USER:
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                lc_messages.append(AIMessage(content=msg.content))

        # 4. Ask the LLM whether this requires a plan or a direct answer.
        classification = await self._classify_intent(user_message.content, lc_messages)

        if classification["needs_plan"]:
            reply = await self._execute_plan(user_message, classification, conversation_id)
        else:
            # Simple conversational reply — no tools needed.
            response = await self._ainvoke_with_retry(lc_messages)
            reply = response.content

        # 5. Store assistant reply in short-term memory.
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=reply,
            channel=user_message.channel,
            user_id=user_message.user_id,
        )
        self._short_term.add_message(conversation_id, assistant_msg)

        # 6. Persist to long-term memory for future recall.
        self._long_term.store(
            f"User: {user_message.content}\nAssistant: {reply}",
            metadata={"user_id": user_message.user_id, "channel": user_message.channel},
        )

        return reply

    # -- internal helpers ------------------------------------------------------

    def _build_system_prompt(self, memory_context: str) -> str:
        tools_desc = "\n".join(
            f"- {t['name']}: {t['description']} (yikici={t['destructive']})"
            for t in self._registry.list_tools()
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
            "KURAL 4: KOTA HATASI (429) ALIRSAN ASLA PES ETME, "
            "DİĞER API ANAHTARINA GEÇ VE İŞLEMİ TAMAMLA! "
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
            tool = self._registry.get(step.tool_name)

            if tool is None:
                learning = self._create_tool_learning_plan(step, user_message)
                step.status = StepStatus.FAILED
                step.error = f"Unknown tool: {step.tool_name}"
                fallback_json = json.dumps(learning, ensure_ascii=True)
                results_summary.append(
                    f"[FAIL] {step.description}: {step.error} | fallback={fallback_json}"
                )
                continue

            temp_input = ToolInput(tool_name=step.tool_name, parameters=step.parameters)
            tool_input = ToolInput(
                tool_name=step.tool_name,
                parameters=step.parameters,
                requires_approval=tool.requires_approval(temp_input),
            )

            policy_decision = self._policy.evaluate(step)
            if not policy_decision.allowed:
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
                    user_id=user_message.user_id,
                )
                continue

            # Guardian check for destructive actions.
            if tool.requires_approval(tool_input) or policy_decision.require_confirmation:
                step.status = StepStatus.AWAITING_APPROVAL
                if policy_decision.require_double_confirmation:
                    approval = await self._guardian.request_critical_approval(
                        action_description=(
                            f"{step.tool_name}: {step.description} | risk={step.risk_level.value}"
                        ),
                        user_id=user_message.user_id,
                    )
                else:
                    approval = await self._guardian.request_approval(
                        action_description=(
                            f"{step.tool_name}: {step.description} | risk={step.risk_level.value}"
                        ),
                        user_id=user_message.user_id,
                    )
                if approval != ApprovalResult.APPROVED:
                    step.status = StepStatus.SKIPPED
                    reason = "denied" if approval == ApprovalResult.DENIED else "timed out"
                    step.error = f"Action {reason} by user"
                    results_summary.append(f"[SKIPPED] {step.description}: {step.error}")
                    await self._state.log_audit(
                        "hitl_rejected",
                        step.description,
                        user_id=user_message.user_id,
                    )
                    continue

            # Execute with recovery.
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
                user_id=user_message.user_id,
            )

        # Finalize plan.
        if plan.is_complete:
            plan.mark_complete()
        else:
            failed = [s for s in plan.steps if s.status == StepStatus.FAILED]
            if failed:
                plan.mark_failed("; ".join(s.error for s in failed))

        await self._state.save_task(
            plan.id, plan.user_request, plan.status.value, plan.model_dump_json()
        )

        # Ask the LLM to summarise the results into a user-friendly reply.
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

        likely_cli = step.tool_name.startswith(("terminal_", "dev_", "net_", "web_"))
        if explicit is not True and not likely_cli:
            return None

        error_text = str(getattr(primary_output, "error", "") or "").lower()
        retryable = any(
            marker in error_text
            for marker in (
                "timeout",
                "timed out",
                "permission",
                "not found",
                "could not",
                "failed",
            )
        )
        if explicit is not True and not retryable:
            return None

        source_query = str(params.get("query") or user_message.content or "")
        source_url = str(params.get("url") or "")
        fallback_input = ToolInput(
            tool_name="gui_autonomous_explorer",
            parameters={
                "goal": (
                    f"Primary step failed ({step.tool_name}): {step.description}. "
                    f"Original request: {user_message.content}"
                ),
                "source_tool": step.tool_name,
                "source_error": str(getattr(primary_output, "error", "") or ""),
                "query": source_query,
                "url": source_url,
                "max_steps": int(params.get("fallback_steps", 4) or 4),
            },
            requires_approval=fallback_tool.is_destructive,
        )
        fallback_input.parameters["max_steps"] = int(
            params.get("fallback_steps", self._settings.hybrid_fallback_max_steps)
            or self._settings.hybrid_fallback_max_steps
        )

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

            # Secondary fallback sequence (Windows): Win+R -> type target -> Enter -> OCR
            # This keeps behavior human-like when primary GUI explorer cannot complete.
            if os.name == "nt":
                hotkey_tool = self._registry.get("gui_press_hotkey")
                type_tool = self._registry.get("gui_type_text")
                analyze_tool = self._registry.get("gui_analyze_screen")

                if hotkey_tool and type_tool and analyze_tool:
                    target = source_url.strip()
                    if not target:
                        query_encoded = source_query.strip().replace(" ", "+")
                        target = f"https://www.google.com/search?q={query_encoded}"

                    sequence_tools = [hotkey_tool, type_tool, analyze_tool]
                    if any(
                        t.requires_approval(ToolInput(tool_name=t.name, parameters={}))
                        for t in sequence_tools
                    ):
                        approval = await self._guardian.request_approval(
                            action_description=(
                                "GUI fallback sequence: gui_press_hotkey + "
                                "gui_type_text + gui_analyze_screen"
                            ),
                            user_id=user_message.user_id,
                        )
                        if approval != ApprovalResult.APPROVED:
                            return None

                    step_hotkey = await self._recovery.execute_with_retry(
                        hotkey_tool,
                        ToolInput(
                            tool_name="gui_press_hotkey",
                            parameters={"keys": ["win", "r"]},
                            requires_approval=hotkey_tool.is_destructive,
                        ),
                        step,
                    )
                    if step_hotkey.status.value != "success":
                        return None

                    step_type = await self._recovery.execute_with_retry(
                        type_tool,
                        ToolInput(
                            tool_name="gui_type_text",
                            parameters={"text": target, "interval": 0.01},
                            requires_approval=type_tool.is_destructive,
                        ),
                        step,
                    )
                    if step_type.status.value != "success":
                        return None

                    step_enter = await self._recovery.execute_with_retry(
                        hotkey_tool,
                        ToolInput(
                            tool_name="gui_press_hotkey",
                            parameters={"keys": ["enter"]},
                            requires_approval=hotkey_tool.is_destructive,
                        ),
                        step,
                    )
                    if step_enter.status.value != "success":
                        return None

                    step_ocr = await self._recovery.execute_with_retry(
                        analyze_tool,
                        ToolInput(
                            tool_name="gui_analyze_screen",
                            parameters={"max_chars": 5000},
                            requires_approval=analyze_tool.is_destructive,
                        ),
                        step,
                    )
                    if step_ocr.status.value == "success":
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
