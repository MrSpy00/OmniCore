"""Centralized settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

import sys

def _resolve_project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / ".env").exists():
            return exe_dir
        if (exe_dir.parent / ".env").exists():
            return exe_dir.parent
        if (Path.cwd() / ".env").exists():
            return Path.cwd()
        return exe_dir
    return Path(__file__).resolve().parent.parent

_PROJECT_ROOT = _resolve_project_root()


# ---------------------------------------------------------------------------
# Available LLM models per provider — used by the model discovery system.
# Only models that are currently live and widely accessible are listed.
# ---------------------------------------------------------------------------
AVAILABLE_GROQ_MODELS: list[dict[str, str]] = [
    {"id": "openai/gpt-oss-20b", "name": "GPT OSS 20B", "context": "128k", "speed": "fastest"},
    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "context": "128k", "speed": "fast"},
    {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": "32k", "speed": "fast"},
    {"id": "gemma2-9b-it", "name": "Gemma 2 9B IT", "context": "8k", "speed": "fast"},
    {
        "id": "llama-3.3-70b-versatile",
        "name": "Llama 3.3 70B",
        "context": "128k",
        "speed": "medium",
    },
    {
        "id": "llama-3.1-8b-instant",
        "name": "Llama 3.1 8B Instant",
        "context": "128k",
        "speed": "fastest",
    },
    {"id": "llama3-70b-8192", "name": "Llama 3 70B", "context": "8k", "speed": "medium"},
    {"id": "llama3-8b-8192", "name": "Llama 3 8B", "context": "8k", "speed": "fastest"},
    {
        "id": "deepseek-r1-distill-llama-70b",
        "name": "DeepSeek R1 Distill 70B",
        "context": "128k",
        "speed": "medium",
    },
    {"id": "qwen-qwq-32b", "name": "Qwen QwQ 32B", "context": "128k", "speed": "medium"},
    {
        "id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "name": "Llama 4 Scout 17B",
        "context": "128k",
        "speed": "fast",
    },
]

AVAILABLE_GEMINI_MODELS: list[dict[str, str]] = [
    # Gemini 2.5 (current generation)
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "context": "1M", "speed": "fastest"},
    {
        "id": "gemini-2.5-flash-lite",
        "name": "Gemini 2.5 Flash Lite",
        "context": "1M",
        "speed": "fastest",
    },
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "context": "2M", "speed": "medium"},
    # Gemini 2.0 (previous gen — still available)
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "context": "1M", "speed": "fastest"},
    {
        "id": "gemini-2.0-flash-lite",
        "name": "Gemini 2.0 Flash Lite",
        "context": "1M",
        "speed": "fastest",
    },
    # Gemini 1.5 (legacy)
    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "context": "2M", "speed": "medium"},
    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "context": "1M", "speed": "fast"},
    {
        "id": "gemini-1.5-flash-8b",
        "name": "Gemini 1.5 Flash 8B",
        "context": "1M",
        "speed": "fastest",
    },
]

AVAILABLE_OPENAI_MODELS: list[dict[str, str]] = [
    {"id": "gpt-4o", "name": "GPT-4o", "context": "128k", "speed": "fast"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context": "128k", "speed": "fastest"},
    {"id": "gpt-4.1", "name": "GPT-4.1", "context": "1M", "speed": "fast"},
    {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini", "context": "1M", "speed": "fastest"},
    {"id": "gpt-4.1-nano", "name": "GPT-4.1 Nano", "context": "1M", "speed": "fastest"},
    {"id": "o3-mini", "name": "o3-mini (Reasoning)", "context": "200k", "speed": "medium"},
    {"id": "o4-mini", "name": "o4-mini (Reasoning)", "context": "200k", "speed": "medium"},
]

AVAILABLE_ANTHROPIC_MODELS: list[dict[str, str]] = [
    {"id": "claude-opus-4-5", "name": "Claude Opus 4.5", "context": "200k", "speed": "slow"},
    {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "context": "200k", "speed": "medium"},
    {"id": "claude-haiku-3-5", "name": "Claude Haiku 3.5", "context": "200k", "speed": "fastest"},
    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "context": "200k", "speed": "slow"},
    {
        "id": "claude-3-5-sonnet-20241022",
        "name": "Claude 3.5 Sonnet",
        "context": "200k",
        "speed": "medium",
    },
]

AVAILABLE_DEEPSEEK_MODELS: list[dict[str, str]] = [
    {"id": "deepseek-chat", "name": "DeepSeek Chat V3", "context": "64k", "speed": "fast"},
    {
        "id": "deepseek-reasoner",
        "name": "DeepSeek Reasoner R1",
        "context": "64k",
        "speed": "medium",
    },
]

AVAILABLE_MISTRAL_MODELS: list[dict[str, str]] = [
    {"id": "mistral-large-latest", "name": "Mistral Large", "context": "128k", "speed": "medium"},
    {"id": "mistral-small-latest", "name": "Mistral Small", "context": "32k", "speed": "fast"},
    {"id": "codestral-latest", "name": "Codestral", "context": "32k", "speed": "fast"},
    {"id": "open-mixtral-8x22b", "name": "Mixtral 8x22B", "context": "64k", "speed": "medium"},
]

AVAILABLE_OLLAMA_MODELS: list[dict[str, str]] = [
    {"id": "llama3.2", "name": "Llama 3.2 (local)", "context": "128k", "speed": "varies"},
    {"id": "llama3.1", "name": "Llama 3.1 (local)", "context": "128k", "speed": "varies"},
    {"id": "mistral", "name": "Mistral (local)", "context": "32k", "speed": "varies"},
    {"id": "gemma2", "name": "Gemma 2 (local)", "context": "8k", "speed": "varies"},
    {"id": "qwen2.5", "name": "Qwen 2.5 (local)", "context": "128k", "speed": "varies"},
    {"id": "phi4", "name": "Phi-4 (local)", "context": "16k", "speed": "varies"},
    {"id": "deepseek-r1", "name": "DeepSeek R1 (local)", "context": "64k", "speed": "varies"},
]


AVAILABLE_PROVIDERS: dict[str, list[dict[str, str]]] = {
    "gemini": AVAILABLE_GEMINI_MODELS,
    "groq": AVAILABLE_GROQ_MODELS,
    "openai": AVAILABLE_OPENAI_MODELS,
    "anthropic": AVAILABLE_ANTHROPIC_MODELS,
    "deepseek": AVAILABLE_DEEPSEEK_MODELS,
    "mistral": AVAILABLE_MISTRAL_MODELS,
    "ollama": AVAILABLE_OLLAMA_MODELS,
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

    # Google Gemini
    google_api_key: str = ""
    google_api_key_2: str = ""
    google_api_key_3: str = ""
    # Default to gemini-2.5-flash (gemini-2.0-flash was deprecated)
    omni_llm_model: str = "gemini-2.5-flash"

    @field_validator("omni_llm_model", mode="before")
    @classmethod
    def _validate_omni_llm_model(cls, v: object) -> str:
        if not v:
            return "gemini-2.5-flash"
        val = str(v).strip().lower()
        if val in ("gemini-2.0-flash", "gemini-2.0-flash-exp", "2.0-flash"):
            return "gemini-2.5-flash"
        if val in ("gemini-2.0-flash-lite", "2.0-flash-lite"):
            return "gemini-2.5-flash-lite"
        return str(v).strip()

    # Groq
    groq_api_key: str = ""
    groq_api_key_1: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_primary_model: str = "openai/gpt-oss-20b"
    groq_fallback_model_1: str = "openai/gpt-oss-120b"
    groq_fallback_model_2: str = "mixtral-8x7b-32768"
    groq_llm_model: str = "openai/gpt-oss-20b"
    groq_fallback_models: str = "openai/gpt-oss-120b,mixtral-8x7b-32768"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""  # empty = use official OpenAI endpoint

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-3-5"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Mistral
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"

    # LLM general
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 4096

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

        Supported providers in current runtime: groq, gemini, openai, anthropic,
        deepseek, mistral, ollama.
        """
        primary = (self.llm_provider or "").strip().lower() or "gemini"
        fallback_tokens = [
            token.strip().lower() for token in self.llm_fallback_order.split(",") if token.strip()
        ]
        supported = list(AVAILABLE_PROVIDERS.keys())

        ordered: list[str] = []
        for candidate in [primary, *fallback_tokens, *supported]:
            if candidate in supported and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    @property
    def provider_availability(self) -> dict[str, bool]:
        """Return whether each provider has at least one usable API key."""
        return {
            "groq": any(key.strip() for key in self.groq_api_keys),
            "gemini": any(key.strip() for key in self.google_api_keys),
            "openai": bool(self.openai_api_key.strip()),
            "anthropic": bool(self.anthropic_api_key.strip()),
            "deepseek": bool(self.deepseek_api_key.strip()),
            "mistral": bool(self.mistral_api_key.strip()),
            "ollama": self.ollama_enabled,
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
    approval_mode: str = "ask"  # ask, safe, or yes/full (persisted via APPROVAL_MODE)

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

    # --- Personalization -----------------------------------------------------
    user_name: str = ""  # Optional display name (empty = use "OmniCore")
    # Internal system name — never changes
    system_name: str = "OmniCore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of the application settings."""
    return Settings()


def invalidate_settings_cache() -> None:
    """Clear the cached Settings singleton so next get_settings() re-reads env."""
    get_settings.cache_clear()


def get_available_models(provider: str | None = None) -> dict[str, list[dict[str, str]]]:
    """Return available LLM models for one or all providers.

    Parameters
    ----------
    provider:
        If specified, return models only for that provider. If ``None``,
        return models for all providers.

    Returns
    -------
    dict
        Provider-keyed dict of model lists.
    """
    if provider is None:
        return dict(AVAILABLE_PROVIDERS)
    normalized = (provider or "").strip().lower()
    if normalized in AVAILABLE_PROVIDERS:
        return {normalized: AVAILABLE_PROVIDERS[normalized]}
    return {}
