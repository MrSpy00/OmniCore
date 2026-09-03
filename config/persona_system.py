"""OmniCore Persona & Öğrenen Tercih Sistemi (Self-Learning Persona System).

Kullanıcı tercihlerini, tarayıcı alışkanlıklarını, dil ve izin modlarını
otomatik olarak öğrenen, güven skoruyla (confidence) pekiştiren ve istenildiğinde
manuel olarak da yapılandırılabilen akıllı persona katmanı.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)

_OMNICORE_DIR = Path(__file__).resolve().parent.parent / ".omnicore"
_PERSONA_FILE = _OMNICORE_DIR / "persona.json"
_PROFILE_TEMPLATE_FILE = _OMNICORE_DIR / "omnicore_profile.json"
_LEARNING_LOG_FILE = _OMNICORE_DIR / "persona_learning.jsonl"


@dataclass
class YoutubePreferences:
    auto_skip_ads: bool = True
    dismiss_premium_modals: bool = True
    enable_notifications: bool = True
    default_playback_speed: float = 1.0
    remember_playback_position: bool = True


@dataclass
class PersonaProfile:
    """OmniCore kullanıcı persona profili."""

    user_id: str = "mrSpy"
    display_name: str = "OmniCore Kullanıcısı"
    language: str = "tr"  # "tr", "en", "auto"
    permission_mode: str = "full_auto"  # "full_auto", "ask_on_risk", "always_ask"
    preferred_browser: str = "brave"  # "brave", "chrome", "edge", "firefox", "auto"
    preferred_search_engine: str = "google"
    turkish_characters_strict: bool = True
    anti_ai_slop_strict: bool = True
    autonomous_execution: bool = True

    youtube_preferences: dict[str, Any] = field(default_factory=lambda: asdict(YoutubePreferences()))
    llm_preferences: dict[str, Any] = field(
        default_factory=lambda: {
            "primary_provider": "groq",
            "fallback_order": ["groq", "gemini", "openai", "deepseek"],
            "temperature": 0.2,
        }
    )
    learned_weights: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class PersonaManager:
    """OmniCore için tekil (singleton) öğrenen persona yöneticisi."""

    _instance: PersonaManager | None = None

    def __new__(cls) -> PersonaManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._omnicore_dir = _OMNICORE_DIR
        self._persona_file = _PERSONA_FILE
        self._profile_file = _PROFILE_TEMPLATE_FILE
        self._learning_log = _LEARNING_LOG_FILE
        self._omnicore_dir.mkdir(parents=True, exist_ok=True)
        self._profile = self._load_or_create()
        self._initialized = True

    def _load_or_create(self) -> PersonaProfile:
        """Load persona from JSON or create default profile."""
        if self._persona_file.exists():
            try:
                with open(self._persona_file, encoding="utf-8") as f:
                    data = json.load(f)
                    return PersonaProfile(
                        user_id=data.get("user_id", "mrSpy"),
                        display_name=data.get("display_name", "OmniCore Kullanıcısı"),
                        language=data.get("language", "tr"),
                        permission_mode=data.get("permission_mode", "full_auto"),
                        preferred_browser=data.get("preferred_browser", "brave"),
                        preferred_search_engine=data.get("preferred_search_engine", "google"),
                        turkish_characters_strict=data.get("turkish_characters_strict", True),
                        anti_ai_slop_strict=data.get("anti_ai_slop_strict", True),
                        autonomous_execution=data.get("autonomous_execution", True),
                        youtube_preferences=data.get("youtube_preferences", asdict(YoutubePreferences())),
                        llm_preferences=data.get("llm_preferences", {}),
                        learned_weights=data.get("learned_weights", {}),
                        created_at=data.get("created_at", datetime.now(UTC).isoformat()),
                        updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
                    )
            except Exception as exc:
                logger.warning("persona.load_error_fallback_default", error=str(exc))

        default_profile = PersonaProfile()
        self._save_profile(default_profile)
        self._save_baseline_template(default_profile)
        return default_profile

    def _save_profile(self, profile: PersonaProfile) -> None:
        """Atomically persist persona profile with UTF-8 encoding."""
        profile.updated_at = datetime.now(UTC).isoformat()
        temp_file = self._omnicore_dir / f"persona_tmp_{os.getpid()}.json"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(asdict(profile), f, ensure_ascii=False, indent=2)
            temp_file.replace(self._persona_file)
            logger.info("persona.profile_saved", path=str(self._persona_file))
        except Exception as exc:
            logger.error("persona.save_failed", error=str(exc))
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def _save_baseline_template(self, profile: PersonaProfile) -> None:
        """Save baseline profile template for reference/reset."""
        if not self._profile_file.exists():
            try:
                with open(self._profile_file, "w", encoding="utf-8") as f:
                    json.dump(asdict(profile), f, ensure_ascii=False, indent=2)
            except Exception as exc:
                logger.warning("persona.save_template_failed", error=str(exc))

    def get_profile(self) -> PersonaProfile:
        """Return the current active persona profile."""
        return self._profile

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a specific preference key."""
        prof_dict = asdict(self._profile)
        return prof_dict.get(key, default)

    def set_preference(self, key: str, value: Any, reason: str = "manual") -> None:
        """Manually update and persist a persona setting."""
        if hasattr(self._profile, key):
            setattr(self._profile, key, value)
            self._save_profile(self._profile)
            self._log_learning_event("manual_override", key, str(value), confidence=1.0, reason=reason)
            logger.info("persona.preference_updated", key=key, value=value, reason=reason)

    def learn_from_interaction(
        self,
        category: str,
        choice: str,
        confidence: float = 0.8,
        context: str = "",
    ) -> bool:
        """Record an interaction pattern and auto-update persona when threshold is met.

        Args:
            category: Preference category (e.g. 'browser', 'language', 'search_engine', 'permission')
            choice: The value chosen/used (e.g. 'brave', 'tr', 'google', 'full_auto')
            confidence: Confidence score of this single observation (0.0 to 1.0)
            context: Optional context description

        Returns:
            True if an active preference was updated as a result of learning.
        """
        category = category.lower().strip()
        choice = choice.lower().strip()

        weights = self._profile.learned_weights
        if category not in weights:
            weights[category] = {}

        cat_weights = weights[category]
        if choice not in cat_weights:
            cat_weights[choice] = {"count": 0, "confidence": 0.0, "last_observed": ""}

        entry = cat_weights[choice]
        old_count = entry.get("count", 0)
        old_conf = entry.get("confidence", 0.0)

        new_count = old_count + 1
        new_conf = round((old_conf * old_count + confidence) / new_count, 3)

        entry["count"] = new_count
        entry["confidence"] = new_conf
        entry["last_observed"] = datetime.now(UTC).isoformat()

        self._log_learning_event(category, choice, str(choice), confidence=confidence, reason=context)

        # Learning trigger: If confidence >= 0.75 and count >= 2, apply preference update
        updated = False
        if new_conf >= 0.75 and new_count >= 2:
            if category in ("browser", "preferred_browser"):
                if self._profile.preferred_browser != choice:
                    self._profile.preferred_browser = choice
                    updated = True
            elif category in ("language", "lang"):
                if self._profile.language != choice:
                    self._profile.language = choice
                    updated = True
            elif category in ("search_engine", "preferred_search_engine"):
                if self._profile.preferred_search_engine != choice:
                    self._profile.preferred_search_engine = choice
                    updated = True
            elif category in ("permission", "permission_mode"):
                if self._profile.permission_mode != choice:
                    self._profile.permission_mode = choice
                    updated = True

        self._save_profile(self._profile)
        if updated:
            logger.info("persona.auto_learned_and_applied", category=category, choice=choice, confidence=new_conf)
        return updated

    def _log_learning_event(
        self,
        event_type: str,
        target: str,
        value: str,
        confidence: float,
        reason: str = "",
    ) -> None:
        """Append learning event to jsonl audit log."""
        try:
            entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": event_type,
                "target": target,
                "value": value,
                "confidence": confidence,
                "reason": reason,
            }
            with open(self._learning_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_system_prompt_context(self) -> str:
        """Generate high-compliance Turkish system prompt injection adhering to learned persona."""
        p = self._profile
        return (
            "\n### OmniCore Öğrenen Persona & Kullanıcı Tercihleri\n"
            f"- **Kullanıcı:** {p.display_name} ({p.user_id})\n"
            f"- **Tercih Edilen Dil:** {p.language.upper()} "
            "(Bütün yanıtlarda ve loglarda tam Türkçe Unicode "
            "ç, ğ, ı, İ, ö, ş, ü karakterleri eksiksiz kullanılmalıdır).\n"
            f"- **İzin ve Otonomi Modu:** {p.permission_mode} "
            "(Güvenli, okuma ve tarayıcı işlemlerinde sormadan doğrudan icra et; gereksiz onay sorma).\n"
            f"- **Varsayılan Tarayıcı:** {p.preferred_browser} "
            "(İşlemleri kullanıcının gerçek tarayıcısında ve kalıcı oturumunda yürüt).\n"
            f"- **Arama Motoru:** {p.preferred_search_engine}\n"
            "- **Kod ve Çıktı Standardı:** AI-slop barındırmayan, el işçiliği kalitesinde, "
            "DRY, modüler ve yüksek performanslı kod.\n"
            "- **YouTube Kuralları:** Reklam ve YouTube Premium pop-up'larını otomatik kapat, "
            "bildirim ve oynatma isteklerini tek pencerede kalıcı oturumla yönet.\n"
        )


def get_persona_manager() -> PersonaManager:
    """Access the singleton PersonaManager instance."""
    return PersonaManager()
