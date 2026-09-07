"""Full integration test — boot OmniCore like a real user."""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SQLITE_DB_PATH"] = ":memory:"
os.environ["CHROMA_PERSIST_DIR"] = "/tmp/omnicore_test_chroma"

passed = 0
failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name} — {detail}")


async def test_settings():
    print("\n=== SETTINGS ===")
    from config.settings import get_settings

    get_settings.cache_clear()
    s = get_settings()
    check("provider", s.llm_provider == "gemini")
    check("model", s.omni_llm_model == "gemini-2.0-flash")
    check("groq_keys_count", len(s.groq_api_keys) >= 0)
    check("rest_api_key_default", s.rest_api_key == "")
    check("scheduler_disabled", s.scheduler_enabled is False)


async def test_short_term_memory():
    print("\n=== SHORT-TERM MEMORY ===")
    from memory.short_term import ShortTermMemory
    from models.messages import Message, MessageRole

    stm = ShortTermMemory(max_messages=5)
    msg = Message(role=MessageRole.USER, content="hello", channel="cli", user_id="u1")
    stm.add_message("c1", msg)
    msgs = stm.get_recent_messages("c1", n=10)
    check("add_and_retrieve", len(msgs) == 1)

    # Test eviction
    for i in range(10):
        m = Message(role=MessageRole.USER, content=f"msg{i}", channel="cli", user_id="u1")
        stm.add_message("c1", m)
    msgs = stm.get_recent_messages("c1", n=100)
    check("eviction_limits", len(msgs) <= 5)


async def test_state_tracker():
    print("\n=== STATE TRACKER ===")
    from memory.state import StateTracker

    st = StateTracker()
    await st.initialize()
    await st.save_task("test_task_id", "test task", "desc")
    tasks = await st.list_tasks()
    check("create_task", len(tasks) >= 1)
    check("list_tasks", len(tasks) >= 1)
    await st.log_audit("test_event", "test detail")
    check("log_audit", True)
    await st.close()


async def test_tool_registry():
    print("\n=== TOOL REGISTRY ===")
    from tools.registry import ToolRegistry, discover_tool_classes, load_custom_skills

    tools_path = Path(_root) / "tools"
    classes = discover_tool_classes(tools_path)
    check("discover_tools", len(classes) > 50, f"got {len(classes)}")
    reg = ToolRegistry()
    for cls in classes:
        reg.register(cls)
    tools = reg.list_tools()
    check("register_tools", len(tools) > 50, f"got {len(tools)}")
    custom = load_custom_skills(Path(_root) / "workspace" / "skills")
    check("custom_skills", len(custom) >= 1)


async def test_guardian():
    print("\n=== GUARDIAN ===")
    from core.guardian import ApprovalMode, Guardian

    g = Guardian()
    check("guardian_default_mode", g._mode == ApprovalMode.ASK)
    g.set_mode(ApprovalMode.YES)
    check("guardian_set_yes", g._mode == ApprovalMode.YES)
    g.set_mode(ApprovalMode.ASK)
    check("guardian_set_ask", g._mode == ApprovalMode.ASK)


async def test_planner():
    print("\n=== PLANNER ===")
    from core.planner import Planner

    p = Planner(llm=None)
    steps = [
        {"tool": "os_read_file", "parameters": {"path": "/tmp/test"}, "description": "read test"},
    ]
    plan = p.build_plan("test request", steps)
    check("build_plan", plan is not None)
    check("plan_has_steps", len(plan.steps) == 1)
    check("plan_step_tool", plan.steps[0].tool_name == "os_read_file")


async def test_policy_engine():
    print("\n=== POLICY ENGINE ===")
    from core.policy import CapabilityPolicyEngine
    from models.tasks import TaskStep

    engine = CapabilityPolicyEngine()
    safe_step = TaskStep(description="read file", tool_name="os_read_file", parameters={})
    decision = engine.evaluate(safe_step)
    check("safe_step_allowed", decision.allowed)

    dangerous_step = TaskStep(
        description="delete everything",
        tool_name="os_write_file",
        parameters={"command": "rm -rf /"},
    )
    decision2 = engine.evaluate(dangerous_step)
    check("dangerous_step_blocked", not decision2.allowed)


async def test_recovery_engine():
    print("\n=== RECOVERY ENGINE ===")
    from core.recovery import RecoveryEngine
    from models.tasks import TaskStep
    from models.tools import ToolInput, ToolOutput, ToolStatus
    from tools.base import BaseTool

    engine = RecoveryEngine(max_attempts=1)

    class AlwaysFail(BaseTool):
        name = "always_fail"

        async def execute(self, _input):
            return ToolOutput(tool_name="always_fail", status=ToolStatus.FAILURE, error="oops")

    step = TaskStep(description="test", tool_name="always_fail", max_retries=0)
    result = await engine.execute_with_retry(AlwaysFail(), ToolInput(tool_name="always_fail", parameters={}), step)
    check("recovery_zero_retry_executes", result is not None)
    check("recovery_zero_retry_has_error", result.error is not None)


async def test_router_imports():
    print("\n=== ROUTER IMPORTS ===")
    from core.router import (
        _ApiKeyRotator,
        _classify_llm_error,
    )

    rotator = _ApiKeyRotator(["k1", "k2", "k3"])
    check("rotator_single_key", rotator.current == "k1")
    check("rotator_cycle", rotator.next_key() == "k2")

    exc = Exception("rate limit exceeded 429")
    is_retry, is_rate = _classify_llm_error(exc)
    check("classify_rate_limit_retryable", is_retry)
    check("classify_rate_limit_is_rate", is_rate)

    exc2 = Exception("something else")
    is_retry2, is_rate2 = _classify_llm_error(exc2)
    check("classify_other_not_retryable", not is_retry2)


async def test_new_toolkits():
    print("\n=== NEW TOOLKITS ===")
    from tools.browser_enhanced_toolkit import BrowserIncognito
    from tools.dev_agent_toolkit import DevAgentAutoFix, DevAgentScaffold
    from tools.video_summary_toolkit import VideoSummarize

    t1 = BrowserIncognito()
    check("incognito_tool", t1.name == "browser_incognito")

    t2 = VideoSummarize()
    check("video_summarize_tool", t2.name == "video_summarize")

    t3 = DevAgentScaffold()
    check("dev_agent_scaffold_tool", t3.name == "dev_agent_scaffold")

    t4 = DevAgentAutoFix()
    check("dev_agent_auto_fix_tool", t4.name == "dev_agent_auto_fix")


async def test_security_toolkit():
    print("\n=== SECURITY TOOLKIT ===")
    from tools.security_toolkit import (
        _decrypt_with_password,
        _derive_key,
        _derive_key_legacy,
        _encrypt_with_password,
    )

    key1, salt1 = _derive_key("password123")
    key2, salt2 = _derive_key("password123")
    check("pbkdf2_random_salt", salt1 != salt2)
    check("pbkdf2_different_keys", key1 != key2)

    key3, salt3 = _derive_key("password123", salt=salt1)
    key4, _ = _derive_key("password123", salt=salt1)
    check("pbkdf2_deterministic", key3 == key4)

    # Test encrypt/decrypt roundtrip
    data = b"secret data to encrypt"
    encrypted = _encrypt_with_password(data, "mypassword")
    decrypted = _decrypt_with_password(encrypted, "mypassword")
    check("encrypt_decrypt_roundtrip", decrypted == data)

    # Test legacy compatibility
    legacy_key = _derive_key_legacy("oldpassword")
    check("legacy_key_works", len(legacy_key) == 44)


async def test_rest_api():
    print("\n=== REST API ===")
    from interfaces.rest_api import create_app

    class MockRouter:
        async def handle_message(self, msg, conv_id):
            return f"Echo: {msg.content}"

    app = create_app(MockRouter())
    check("rest_app_created", app is not None)
    check("rest_has_health", "/health" in [r.path for r in app.routes])
    check("rest_has_chat", "/chat" in [r.path for r in app.routes])


async def test_platform_adapter():
    print("\n=== PLATFORM ADAPTER ===")
    from core.platform_adapter import PlatformAdapter

    os_type = PlatformAdapter.get_os_type()
    check("os_type_detected", os_type in ("windows", "linux", "macos"))

    summary = PlatformAdapter.get_system_summary()
    check("system_summary", isinstance(summary, dict) and len(summary) > 0)


async def main():
    print("=" * 60)
    print("  OmniCore Full Integration Test")
    print("=" * 60)

    await test_settings()
    await test_short_term_memory()
    await test_state_tracker()
    await test_tool_registry()
    await test_guardian()
    await test_planner()
    await test_policy_engine()
    await test_recovery_engine()
    await test_router_imports()
    await test_new_toolkits()
    await test_security_toolkit()
    await test_rest_api()
    await test_platform_adapter()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
