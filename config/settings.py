"""Centralized settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Available LLM models per provider — used by the model discovery system.
# Only models that are currently live and widely accessible are listed.
# ---------------------------------------------------------------------------
AVAILABLE_GROQ_MODELS: list[dict[str, str]] = [
    {"id": "openai/gpt-oss-20b", "name": "GPT OSS 20B", "context": "128k", "speed": "fastest"},
    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "context": "128k", "speed": "fast"},
    {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": "32k", "speed": "fast"},
    {"id": "gemma2-9b-it", "name": "Gemma 2 9B IT", "context": "8k", "speed": "fast"},
    {"id": "llama3-70b-8192", "name": "Llama 3 70B", "context": "8k", "speed": "medium"},
    {"id": "llama3-8b-8192", "name": "Llama 3 8B", "context": "8k", "speed": "fastest"},
]

AVAILABLE_GEMINI_MODELS: list[dict[str, str]] = [
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "context": "1M", "speed": "fastest"},
    {
        "id": "gemini-2.0-flash-lite",
        "name": "Gemini 2.0 Flash Lite",
        "context": "1M",
        "speed": "fastest",
    },
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "context": "1M", "speed": "fast"},
    {
        "id": "gemini-2.5-flash-preview-05-20",
        "name": "Gemini 2.5 Flash Prev",
        "context": "1M",
        "speed": "fast",
    },
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "context": "1M", "speed": "medium"},
    {
        "id": "gemini-2.5-pro-preview-06-05",
        "name": "Gemini 2.5 Pro Prev",
        "context": "1M",
        "speed": "medium",
    },
    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro Legacy", "context": "2M", "speed": "medium"},
    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash Legacy", "context": "1M", "speed": "fast"},
]

AVAILABLE_PROVIDERS: dict[str, list[dict[str, str]]] = {
    "gemini": AVAILABLE_GEMINI_MODELS,
    "groq": AVAILABLE_GROQ_MODELS,
}


class Settings(BaseSettings):
    """Application-wide configuration.

    Values are loaded from environment variables and/or a .env file located
    at the project root.  Every field has a sensible default so the app can
    boot in development without a .env file (except for API keys).
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM -----------------------------------------------------------------
    llm_provider: str = "gemini"
    llm_fallback_order: str = "groq,gemini"
    google_api_key: str = ""
    google_api_key_2: str = ""
    google_api_key_3: str = ""
    # Primary Gemini model — default updated to 2.0-flash for speed & cost
    omni_llm_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_primary_model: str = "openai/gpt-oss-20b"
    groq_fallback_model_1: str = "openai/gpt-oss-120b"
    groq_fallback_model_2: str = "mixtral-8x7b-32768"
    groq_llm_model: str = "openai/gpt-oss-20b"
    groq_fallback_models: str = "openai/gpt-oss-120b,mixtral-8x7b-32768"
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 4096

    # --- Future provider API keys (for extensibility) -------------------------
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # --- Local Offline LLM Fallback (Ollama / LM Studio) ----------------------
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.2"

    # --- Hybrid fallback -----------------------------------------------------
    hybrid_fallback_enabled: bool = True
    hybrid_fallback_max_steps: int = 4

    # --- Rate Limiting & Concurrency -----------------------------------------
    llm_semaphore_limit: int = 3

    # --- Recovery Engine -----------------------------------------------------
    recovery_max_attempts: int = 2

    # --- Memory ---------------------------------------------------------------
    short_term_max_messages: int = 50
    long_term_n_results: int = 6

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
            chain = ["openai/gpt-oss-20b"]
        return chain

    @property
    def google_api_keys(self) -> list[str]:
        """Return configured Google/Gemini API keys in rotation order."""
        keys = [
            k.strip() for k in (self.google_api_key, self.google_api_key_2, self.google_api_key_3)
        ]
        keys = [k for k in keys if k]
        if not keys:
            return [""]
        return keys

    @property
    def provider_preference(self) -> list[str]:
        """Return provider preference order with the primary provider first.

        Supported providers in current runtime are ``groq`` and ``gemini``.
        """
        primary = (self.llm_provider or "").strip().lower() or "gemini"
        fallback_tokens = [
            token.strip().lower() for token in self.llm_fallback_order.split(",") if token.strip()
        ]
        supported = ["groq", "gemini"]

        ordered: list[str] = []
        for candidate in [primary, *fallback_tokens, *supported]:
            if candidate in supported and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    @property
    def provider_availability(self) -> dict[str, bool]:
        """Return whether each provider has at least one usable API key."""
        groq_available = any(key.strip() for key in self.groq_api_keys)
        gemini_available = any(key.strip() for key in self.google_api_keys)
        return {
            "groq": groq_available,
            "gemini": gemini_available,
        }

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

    # --- Paths ---------------------------------------------------------------
    chroma_persist_dir: Path = Path("./data/chromadb")
    sqlite_db_path: Path = Path("./data/omnicore.db")

    # --- Logging -------------------------------------------------------------
    log_level: str = "INFO"

    # --- Scheduler -----------------------------------------------------------
    scheduler_enabled: bool = True
    scheduler_db_path: Path = Path("./data/apscheduler.db")

    # --- REST API Gateway ----------------------------------------------------
    rest_api_key: str = ""  # Bearer token auth (empty = open mode)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()


def get_available_models(provider: str | None = None) -> dict[str, list[dict[str, str]]]:
    """Return available LLM models for one or all providers.

    Parameters
    ----------
    provider:
        If specified, return models only for that provider (``"gemini"`` or
        ``"groq"``). If ``None``, return models for all providers.

    Returns
    -------
    dict
        ``{"gemini": [...], "groq": [...]}`` or a single-key dict.
    """
    if provider is None:
        return dict(AVAILABLE_PROVIDERS)
    normalized = (provider or "").strip().lower()
    if normalized in AVAILABLE_PROVIDERS:
        return {normalized: AVAILABLE_PROVIDERS[normalized]}
    return {}
