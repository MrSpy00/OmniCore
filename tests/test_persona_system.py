"""Unit tests for OmniCore Persona & Self-Learning System."""


from config.persona_system import get_persona_manager


def test_persona_manager_singleton():
    pm1 = get_persona_manager()
    pm2 = get_persona_manager()
    assert pm1 is pm2


def test_persona_profile_defaults():
    pm = get_persona_manager()
    profile = pm.get_profile()
    assert profile.user_id == "mrSpy"
    assert profile.language == "tr"
    assert profile.turkish_characters_strict is True
    assert profile.permission_mode in ("full_auto", "ask_on_risk", "always_ask")
    assert "auto_skip_ads" in profile.youtube_preferences


def test_persona_manual_set_preference():
    pm = get_persona_manager()
    original_engine = pm.get_preference("preferred_search_engine")
    try:
        pm.set_preference("preferred_search_engine", "duckduckgo", reason="test")
        assert pm.get_preference("preferred_search_engine") == "duckduckgo"
    finally:
        pm.set_preference("preferred_search_engine", original_engine, reason="restore")


def test_persona_auto_learning():
    pm = get_persona_manager()
    # Simulate observing user preferring brave browser multiple times
    pm.learn_from_interaction("browser", "brave", confidence=0.9, context="test_1")
    pm.learn_from_interaction("browser", "brave", confidence=0.95, context="test_2")

    profile = pm.get_profile()
    assert profile.preferred_browser == "brave"
    assert "browser" in profile.learned_weights
    assert "brave" in profile.learned_weights["browser"]
    assert profile.learned_weights["browser"]["brave"]["count"] >= 2


def test_persona_system_prompt_context():
    pm = get_persona_manager()
    context = pm.get_system_prompt_context()
    assert "OmniCore Öğrenen Persona" in context
    assert "TR" in context
    assert "mrSpy" in context
    # Verify strict Turkish Unicode characters exist in prompt
    assert any(c in context for c in ("ç", "ğ", "ı", "İ", "ö", "ş", "ü"))
