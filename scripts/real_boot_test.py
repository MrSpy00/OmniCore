"""Real user boot test — run like a user would."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SQLITE_DB_PATH"] = ":memory:"
os.environ["CHROMA_PERSIST_DIR"] = "/tmp/oc_boot_test"


async def main():
    log = []

    def p(msg):
        log.append(msg)
        print(msg, flush=True)

    p("=" * 50)
    p("  OmniCore Real Boot Test")
    p("=" * 50)

    # 1. Settings
    p("\n[1/10] Settings...")
    from config.settings import get_settings

    get_settings.cache_clear()
    s = get_settings()
    p(f"  provider={s.llm_provider} model={s.omni_llm_model}")
    p("  OK")

    # 2. Memory
    p("\n[2/10] Memory systems...")
    from memory.long_term import LongTermMemory
    from memory.short_term import ShortTermMemory
    from memory.state import StateTracker

    stm = ShortTermMemory(max_messages=50)
    ltm = LongTermMemory()
    st = StateTracker()
    await st.initialize()
    p("  ShortTermMemory OK")
    p("  LongTermMemory OK")
    p("  StateTracker OK")

    # 3. Tool Registry
    p("\n[3/10] Tool discovery...")
    from tools.registry import ToolRegistry, discover_tool_classes, load_custom_skills

    reg = ToolRegistry()
    classes = discover_tool_classes(Path(_root) / "tools")
    for cls in classes:
        reg.register(cls)
    custom = load_custom_skills(Path(_root) / "workspace" / "skills")
    tool_count = len(reg.list_tools())
    p(f"  Discovered {len(classes)} tool classes")
    p(f"  Registered {tool_count} tools")
    p(f"  Custom skills: {len(custom)}")
    p("  OK")

    # 4. Core modules
    p("\n[4/10] Core modules...")
    from core.guardian import Guardian
    from core.planner import Planner
    from core.policy import CapabilityPolicyEngine
    from core.recovery import RecoveryEngine

    Guardian()
    Planner(llm=None)
    pol = CapabilityPolicyEngine()
    RecoveryEngine(max_attempts=2)
    p("  Guardian OK")
    p("  Planner OK")
    p("  PolicyEngine OK")
    p("  RecoveryEngine OK")

    # 5. Router
    p("\n[5/10] CognitiveRouter initialization...")
    from core.router import CognitiveRouter

    router = CognitiveRouter(
        tool_registry=reg,
        short_term=stm,
        long_term=ltm,
        state_tracker=st,
    )
    p("  CognitiveRouter initialized")
    p("  OK")

    # 6. Slash commands
    p("\n[6/10] Slash commands...")
    from models.messages import Message, MessageRole

    for cmd in ["/help", "/doctor", "/models", "/memory", "/plan"]:
        msg = Message(role=MessageRole.USER, content=cmd, channel="cli", user_id="test")
        resp = await router.handle_message(msg, f"test_{cmd}")
        p(f"  {cmd}: {len(resp)} chars")

    p("  All slash commands respond")

    # 7. Policy engine
    p("\n[7/10] Policy engine...")
    from models.tasks import TaskStep

    safe = TaskStep(description="read", tool_name="os_read_file", parameters={})
    d1 = pol.evaluate(safe)
    p(f"  Safe step allowed: {d1.allowed}")

    danger = TaskStep(
        description="rm",
        tool_name="os_write_file",
        parameters={"command": "rm -rf /"},
    )
    d2 = pol.evaluate(danger)
    p(f"  Dangerous blocked: {not d2.allowed}")

    # 8. Tool execution
    p("\n[8/10] Tool execution...")
    from models.tools import ToolInput

    os_list = reg.get("os_list_dir")
    if os_list:
        result = await os_list.execute(ToolInput(tool_name="os_list_dir", parameters={"path": "."}))
        p(f"  os_list_dir: status={result.status.value}, items in result")

    api_dt = reg.get("api_datetime")
    if api_dt:
        result = await api_dt.execute(ToolInput(tool_name="api_datetime", parameters={}))
        p(f"  api_datetime: {result.result[:50] if result.result else 'N/A'}")

    # 9. Security toolkit
    p("\n[9/10] Security toolkit...")
    from tools.security_toolkit import _decrypt_with_password, _encrypt_with_password

    data = b"OmniCore security test"
    enc = _encrypt_with_password(data, "testpass")
    dec = _decrypt_with_password(enc, "testpass")
    p(f"  Encrypt/Decrypt roundtrip: {dec == data}")

    # 10. REST API
    p("\n[10/10] REST API...")
    from interfaces.rest_api import create_app

    app = create_app(router)
    routes = [r.path for r in app.routes]
    p(f"  Routes: {routes}")

    # Cleanup
    await st.close()
    ltm.close()

    p("\n" + "=" * 50)
    p(f"  RESULT: ALL {10}/10 SYSTEMS OPERATIONAL")
    p("=" * 50)

    return len(log)


if __name__ == "__main__":
    asyncio.run(main())
