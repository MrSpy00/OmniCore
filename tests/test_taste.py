"""Unit tests for TasteEngine in memory/taste.py."""

from __future__ import annotations

import pytest

from memory.taste import TasteEngine, get_taste_engine


class TestTasteEngine:
    """Test user preference learning, storage, formatting, and feedback."""

    @pytest.fixture()
    def engine(self, tmp_path):
        db_file = tmp_path / "test_taste.db"
        return TasteEngine(db_path=db_file)

    def test_singleton(self):
        e1 = get_taste_engine()
        e2 = get_taste_engine()
        assert e1 is e2

    def test_learn_and_get(self, engine):
        engine.learn("language", "primary", "turkish", confidence=0.8)
        val = engine.get("language", "primary")
        assert val == "turkish"

    def test_learn_update_conflict(self, engine):
        engine.learn("language", "primary", "english", confidence=0.7)
        engine.learn("language", "primary", "turkish", confidence=0.9)

        assert engine.get("language", "primary") == "turkish"
        all_tastes = engine.get_all("language")
        assert len(all_tastes) == 1
        assert all_tastes[0]["confidence"] == 0.9

    def test_feedback_positive_and_negative(self, engine):
        engine.learn("ui_preferences", "theme", "dark", confidence=0.5)

        # Positive feedback increases confidence
        engine.feedback("ui_preferences", "theme", "positive")
        prefs = engine.get_all("ui_preferences")
        assert prefs[0]["confidence"] == 0.65

        # Negative feedback decreases confidence
        engine.feedback("ui_preferences", "theme", "wrong")
        prefs = engine.get_all("ui_preferences")
        assert abs(prefs[0]["confidence"] - 0.45) < 1e-4

    def test_forget_single_and_all(self, engine):
        engine.learn("content", "media", "youtube")
        engine.learn("content", "dev", "github")
        engine.learn("language", "primary", "tr")

        # Forget one key
        deleted = engine.forget("content", "media")
        assert deleted == 1
        assert engine.get("content", "media") is None
        assert engine.get("content", "dev") == "github"

        # Forget entire category
        deleted = engine.forget("content")
        assert deleted == 1
        assert len(engine.get_all("content")) == 0

        # Forget all
        deleted = engine.forget()
        assert deleted >= 1
        assert len(engine.get_all()) == 0

    def test_format_for_system_prompt(self, engine):
        engine.learn("language", "primary", "turkish", confidence=0.9)
        engine.learn("response_style", "length", "concise", confidence=0.8)
        engine.learn("low_conf", "ignore_me", "none", confidence=0.2)  # Should be filtered (< 0.4)

        prompt_block = engine.format_for_system_prompt()
        assert "KULLANICI TERCİHLERİ" in prompt_block
        assert "primary: turkish" in prompt_block
        assert "length: concise" in prompt_block
        assert "ignore_me" not in prompt_block

    def test_format_for_system_prompt_empty(self, engine):
        assert engine.format_for_system_prompt() == ""

    def test_auto_learn_from_interaction(self, engine):
        # Turkish detection
        engine.auto_learn_from_interaction(
            user_message="Merhaba, bana yardım edebilir misin?",
            assistant_response="Elbette!",
            tools_used=["bash_tool", "python_tool"],
        )
        assert engine.get("language", "primary") == "turkish"
        assert engine.get("tool_preferences", "bash_tool") == "1"

        # English concise detection
        engine.auto_learn_from_interaction(
            user_message="Hello, please keep it brief and short.",
            assistant_response="Sure.",
        )
        assert engine.get("response_style", "length") == "concise"

        # Auto-approval detection
        engine.auto_learn_from_interaction(
            user_message="Artık onay sorma, her şeyi otomatik onayla",
            assistant_response="Anlaşıldı.",
        )
        assert engine.get("behavior", "approval") == "auto"

    @pytest.mark.asyncio
    async def test_async_methods(self, engine):
        await engine.learn_async("provider_preferences", "primary", "groq", confidence=0.85)
        val = await engine.get_async("provider_preferences", "primary")
        assert val == "groq"

        all_prefs = await engine.get_all_async("provider_preferences")
        assert len(all_prefs) == 1

        prompt_str = await engine.format_for_system_prompt_async()
        assert "groq" in prompt_str

        await engine.auto_learn_from_interaction_async("Selam!", "Merhaba!")
        assert await engine.get_async("language", "primary") == "turkish"
