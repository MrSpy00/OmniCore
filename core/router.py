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

import json
import re
from typing import Any, Callable, Awaitable

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from config.logging import get_logger
from config.settings import get_settings
from core.guardian import Guardian, ApprovalResult
from core.planner import Planner
from core.recovery import RecoveryEngine
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory
from memory.state import StateTracker
from models.messages import Message, MessageRole
from models.tasks import TaskPlan, StepStatus, TaskStatus
from models.tools import ToolInput
from tools.registry import ToolRegistry

logger = get_logger(__name__)


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
        self._llm = self._build_llm(settings)
        self._planner = Planner(self._llm)
        self._guardian = Guardian(
            timeout_minutes=settings.hitl_timeout_minutes,
            approval_callback=approval_callback,
        )
        self._recovery = RecoveryEngine()

    def _build_llm(self, settings) -> Any:
        provider = settings.llm_provider.strip().lower()
        if provider == "groq":
            return ChatGroq(
                model=settings.groq_llm_model,
                api_key=settings.groq_api_key,
                temperature=settings.llm_temperature,
            )
        if provider in ("", "gemini"):
            return ChatGoogleGenerativeAI(
                model=settings.omni_llm_model,
                google_api_key=settings.google_api_key,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_output_tokens,
            )

        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

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
            response = await self._llm.ainvoke(lc_messages)
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
            f"- {t['name']}: {t['description']} (destructive={t['destructive']})"
            for t in self._registry.list_tools()
        )
        return (
            "You are OmniCore, an autonomous OS Kernel. YOU ARE FORBIDDEN FROM PRETENDING TO DO ACTIONS. "
            "If the user asks for IP, Ping, PC Stats, or any system info, YOU MUST RETURN A JSON PLAN "
            "CALLING THE EXACT TOOL. NEVER simulate a response. NEVER tell the user to check it themselves. "
            "EXECUTE THE TOOL AND WAIT FOR THE RESULT.\n"
            "CRITICAL: DO NOT SAY 'I did it' WITHOUT SHOWING THE DATA. If a tool returns files, IPs, or "
            "stats, you MUST print the actual raw data to the user. DO NOT HIDE INFORMATION.\n"
            "CRITICAL: You are running on WINDOWS 11. When using terminal_execute, you MUST use Windows CMD "
            "or PowerShell commands. DO NOT use Linux commands like whois, ls, or ~ for paths. Use C:\\ paths. "
            "To open an app like Steam, use start steam or PowerShell. Never assume Linux.\n"
            "CRITICAL RULE: DO NOT generate placeholders like [insert date here]. If you do not have data, "
            "you MUST call a tool to get it. DO NOT output raw JSON plans directly to the user.\n\n"
            "## Available Tools\n"
            f"{tools_desc}\n\n"
            "## Relevant Memories\n"
            f"{memory_context or '(none)'}\n\n"
            "## Instructions\n"
            "When the user asks for any system data or action, respond ONLY with a JSON plan.\n"
            "Never answer with general advice like 'open task manager' — use tools.\n"
            '```json\n{"needs_plan": true, "steps": [{"tool": "<tool_name>", "description": "...", '
            '"parameters": {...}, "destructive": true/false}]}\n```\n'
            "Only respond conversationally when no tool can possibly help.\n"
            "Always be concise and helpful."
        )

    async def _classify_intent(self, user_text: str, lc_messages: list) -> dict[str, Any]:
        """Ask the LLM to decide: plan or direct answer."""
        classification_prompt = (
            f"Decide whether the following request requires executing tools "
            f"or is a simple conversational reply.\n"
            f"Request: {user_text}\n\n"
            f"Respond ONLY with JSON: "
            f'{{"needs_plan": true/false, "steps": [...] or []}}'
        )
        lc_messages_copy = list(lc_messages) + [HumanMessage(content=classification_prompt)]

        response = await self._llm.ainvoke(lc_messages_copy)
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
                step.status = StepStatus.FAILED
                step.error = f"Unknown tool: {step.tool_name}"
                results_summary.append(f"[FAIL] {step.description}: {step.error}")
                continue

            temp_input = ToolInput(tool_name=step.tool_name, parameters=step.parameters)
            tool_input = ToolInput(
                tool_name=step.tool_name,
                parameters=step.parameters,
                requires_approval=tool.requires_approval(temp_input),
            )

            # Guardian check for destructive actions.
            if tool.requires_approval(tool_input):
                step.status = StepStatus.AWAITING_APPROVAL
                approval = await self._guardian.request_approval(
                    action_description=f"{step.tool_name}: {step.description}",
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
            f"The user asked: {user_message.content}\n\n"
            f"I executed the following steps:\n"
            + "\n".join(results_summary)
            + "\n\nPlease write a concise summary for the user and include concrete raw values from the tool outputs."
        )
        summary_response = await self._llm.ainvoke([HumanMessage(content=summary_prompt)])
        summary_text = str(summary_response.content)

        if _looks_like_json_plan(summary_text):
            fallback = [line for line in results_summary if line]
            if not fallback:
                return "I could not complete the request due to tool failures."
            return "\n".join(fallback)

        if _contains_placeholder(summary_text):
            fallback = [line for line in results_summary if line]
            if fallback:
                return "\n".join(fallback)
        return summary_text


def _looks_like_json_plan(text: str) -> bool:
    stripped = text.strip()
    if stripped.startswith("{") and '"needs_plan"' in stripped:
        return True
    return stripped.startswith("```") and '"needs_plan"' in stripped


def _contains_placeholder(text: str) -> bool:
    patterns = [
        r"\[.*burada.*\]",
        r"\[.*insert.*\]",
        r"placeholder",
    ]
    lowered = text.lower()
    return any(re.search(p, lowered) for p in patterns)
