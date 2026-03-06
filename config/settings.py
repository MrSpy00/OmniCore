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
    groq_llm_model: str = "llama-3.3-70b-versatile"
    groq_fallback_models: str = "llama-3.1-8b-instant,gemma2-9b-it"
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 4096

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
