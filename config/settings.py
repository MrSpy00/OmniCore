"""Centralized settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration.

    Values are loaded from environment variables and/or a .env file located
    at the project root.  Every field has a sensible default so the app can
    boot in development without a .env file (except for API keys).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM -----------------------------------------------------------------
    llm_provider: str = "gemini"
    google_api_key: str = ""
    omni_llm_model: str = "gemini-1.5-pro"
    groq_api_key: str = ""
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_primary_model: str = "llama-3.1-8b-instant"
    groq_fallback_model_1: str = "llama-3.3-70b-versatile"
    groq_fallback_model_2: str = "mixtral-8x7b-32768"
    groq_llm_model: str = "llama-3.1-8b-instant"
    groq_fallback_models: str = "llama-3.3-70b-versatile,mixtral-8x7b-32768"
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 4096

    @property
    def groq_api_keys(self) -> list[str]:
        """Return all configured Groq API keys in round-robin order.

        Collects GROQ_API_KEY_1, _2, _3 first, then falls back to the
        original GROQ_API_KEY if no numbered keys are set.
        """
        keys = [
            k for k in (self.groq_api_key_1, self.groq_api_key_2, self.groq_api_key_3) if k.strip()
        ]
        if not keys and self.groq_api_key.strip():
            keys = [self.groq_api_key.strip()]
        return keys

    @property
    def groq_model_chain(self) -> list[str]:
        """Return ordered Groq model fallback chain.

        Uses explicit env vars first (PRIMARY/FALLBACK_1/FALLBACK_2), then
        falls back to legacy settings for backward compatibility.
        """
        explicit = [
            self.groq_primary_model.strip(),
            self.groq_fallback_model_1.strip(),
            self.groq_fallback_model_2.strip(),
        ]
        chain = [m for m in explicit if m]

        if not chain and self.groq_llm_model.strip():
            chain.append(self.groq_llm_model.strip())

        legacy = [m.strip() for m in self.groq_fallback_models.split(",") if m.strip()]
        for model_name in legacy:
            if model_name not in chain:
                chain.append(model_name)

        if not chain:
            chain = ["llama-3.1-8b-instant"]
        return chain

    # --- Telegram Gateway ----------------------------------------------------
    telegram_bot_token: str = ""
    telegram_allowed_users: str = ""  # comma-separated user IDs

    @property
    def allowed_user_ids(self) -> list[int]:
        """Parse allowed Telegram user IDs into a list of ints."""
        if not self.telegram_allowed_users.strip():
            return []
        return [int(uid.strip()) for uid in self.telegram_allowed_users.split(",") if uid.strip()]

    # --- HITL Guardian -------------------------------------------------------
    hitl_timeout_minutes: int = 5

    # --- Sandbox & Paths -----------------------------------------------------
    sandbox_root: Path = Path("./workspace")
    chroma_persist_dir: Path = Path("./data/chromadb")
    sqlite_db_path: Path = Path("./data/omnicore.db")

    # --- Logging -------------------------------------------------------------
    log_level: str = "INFO"

    # --- Scheduler -----------------------------------------------------------
    scheduler_enabled: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()
