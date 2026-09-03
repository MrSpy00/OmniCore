"""Centralized settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
# Available LLM models per provider
# ---------------------------------------------------------------------------

AVAILABLE_GEMINI_MODELS: list[dict[str, str]] = [
    {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash", "context": "1M", "speed": "fastest"},
    {"id": "gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite", "context": "1M", "speed": "fastest"},
    {"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro", "context": "2M", "speed": "medium"},
    {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "context": "1M", "speed": "fastest"},
    {"id": "gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash Lite", "context": "1M", "speed": "fastest"},
    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "context": "2M", "speed": "medium"},
    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "context": "1M", "speed": "fast"},
    {"id": "gemini-1.5-flash-8b", "name": "Gemini 1.5 Flash 8B", "context": "1M", "speed": "fastest"},
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
    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "context": "200k", "speed": "medium"},
]

AVAILABLE_XAI_MODELS: list[dict[str, str]] = [
    {"id": "grok-4", "name": "Grok 4", "context": "256k", "speed": "fast"},
    {"id": "grok-3", "name": "Grok 3", "context": "128k", "speed": "medium"},
    {"id": "grok-3-mini", "name": "Grok 3 Mini", "context": "128k", "speed": "fast"},
    {"id": "grok-2-1212", "name": "Grok 2 (1212)", "context": "128k", "speed": "medium"},
    {"id": "grok-2-vision-1212", "name": "Grok 2 Vision", "context": "32k", "speed": "medium"},
    {"id": "grok-beta", "name": "Grok Beta", "context": "128k", "speed": "fast"},
]

AVAILABLE_DEEPSEEK_MODELS: list[dict[str, str]] = [
    {"id": "deepseek-chat", "name": "DeepSeek Chat V3", "context": "64k", "speed": "fast"},
    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner R1", "context": "64k", "speed": "medium"},
]

AVAILABLE_MISTRAL_MODELS: list[dict[str, str]] = [
    {"id": "mistral-large-latest", "name": "Mistral Large", "context": "128k", "speed": "medium"},
    {"id": "mistral-small-latest", "name": "Mistral Small", "context": "32k", "speed": "fast"},
    {"id": "codestral-latest", "name": "Codestral", "context": "32k", "speed": "fast"},
    {"id": "open-mixtral-8x22b", "name": "Mixtral 8x22B", "context": "64k", "speed": "medium"},
]

AVAILABLE_COHERE_MODELS: list[dict[str, str]] = [
    {"id": "command-r-plus-08-2024", "name": "Command R+ (Aug 2024)", "context": "128k", "speed": "medium"},
    {"id": "command-r-08-2024", "name": "Command R (Aug 2024)", "context": "128k", "speed": "fast"},
    {"id": "command-r-plus", "name": "Command R+", "context": "128k", "speed": "medium"},
    {"id": "command-r", "name": "Command R", "context": "128k", "speed": "fast"},
    {"id": "command-light", "name": "Command Light", "context": "4k", "speed": "fastest"},
]

AVAILABLE_AI21_MODELS: list[dict[str, str]] = [
    {"id": "jamba-1.5-large", "name": "Jamba 1.5 Large", "context": "256k", "speed": "medium"},
    {"id": "jamba-1.5-mini", "name": "Jamba 1.5 Mini", "context": "256k", "speed": "fast"},
]

AVAILABLE_PERPLEXITY_MODELS: list[dict[str, str]] = [
    {"id": "sonar", "name": "Perplexity Sonar", "context": "128k", "speed": "fast"},
    {"id": "sonar-pro", "name": "Perplexity Sonar Pro", "context": "200k", "speed": "medium"},
    {"id": "sonar-reasoning", "name": "Perplexity Sonar Reasoning", "context": "128k", "speed": "medium"},
]

AVAILABLE_REKA_MODELS: list[dict[str, str]] = [
    {"id": "reka-core", "name": "Reka Core", "context": "128k", "speed": "medium"},
    {"id": "reka-flash", "name": "Reka Flash", "context": "128k", "speed": "fast"},
    {"id": "reka-edge", "name": "Reka Edge", "context": "64k", "speed": "fastest"},
]

AVAILABLE_WRITER_MODELS: list[dict[str, str]] = [
    {"id": "palmyra-x-004", "name": "Palmyra X 004", "context": "128k", "speed": "fast"},
    {"id": "palmyra-med-70b", "name": "Palmyra Med 70B", "context": "32k", "speed": "medium"},
]

AVAILABLE_GROQ_MODELS: list[dict[str, str]] = [
    {"id": "openai/gpt-oss-20b", "name": "GPT OSS 20B", "context": "128k", "speed": "fastest"},
    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B", "context": "128k", "speed": "fast"},
    {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "context": "32k", "speed": "fast"},
    {"id": "gemma2-9b-it", "name": "Gemma 2 9B IT", "context": "8k", "speed": "fast"},
    {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "context": "128k", "speed": "medium"},
    {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant", "context": "128k", "speed": "fastest"},
    {"id": "llama3-70b-8192", "name": "Llama 3 70B", "context": "8k", "speed": "medium"},
    {"id": "llama3-8b-8192", "name": "Llama 3 8B", "context": "8k", "speed": "fastest"},
    {"id": "deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 Distill 70B", "context": "128k", "speed": "medium"},
    {"id": "qwen-qwq-32b", "name": "Qwen QwQ 32B", "context": "128k", "speed": "medium"},
    {
        "id": "meta-llama/llama-4-scout-17b-16e-instruct",
        "name": "Llama 4 Scout 17B",
        "context": "128k",
        "speed": "fast",
    },
]

# --- OpenAI-uyumlu hızlı inference providerları ---
AVAILABLE_FIREWORKS_MODELS: list[dict[str, str]] = [
    {
        "id": "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "name": "Llama 3.3 70B",
        "context": "128k",
        "speed": "fast",
    },
    {
        "id": "accounts/fireworks/models/mixtral-8x22b-instruct",
        "name": "Mixtral 8x22B",
        "context": "64k",
        "speed": "medium",
    },
    {
        "id": "accounts/fireworks/models/qwen-2.5-72b-instruct",
        "name": "Qwen 2.5 72B",
        "context": "128k",
        "speed": "medium",
    },
    {"id": "accounts/fireworks/models/deepseek-v3", "name": "DeepSeek V3", "context": "64k", "speed": "fast"},
]

AVAILABLE_TOGETHER_MODELS: list[dict[str, str]] = [
    {
        "id": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "name": "Llama 3.3 70B Turbo",
        "context": "128k",
        "speed": "fast",
    },
    {"id": "Qwen/Qwen2.5-72B-Instruct-Turbo", "name": "Qwen 2.5 72B Turbo", "context": "128k", "speed": "fast"},
    {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3", "context": "64k", "speed": "fast"},
    {"id": "mistralai/Mistral-Small-24B-Instruct-2501", "name": "Mistral Small 24B", "context": "32k", "speed": "fast"},
]

AVAILABLE_DEEPINFRA_MODELS: list[dict[str, str]] = [
    {"id": "meta-llama/Meta-Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fast"},
    {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen 2.5 72B", "context": "128k", "speed": "medium"},
    {"id": "deepseek-ai/DeepSeek-V3-0324", "name": "DeepSeek V3", "context": "64k", "speed": "fast"},
]

AVAILABLE_NOVITA_MODELS: list[dict[str, str]] = [
    {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fast"},
    {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "context": "64k", "speed": "medium"},
]

AVAILABLE_CEREBRAS_MODELS: list[dict[str, str]] = [
    {"id": "llama-3.3-70b", "name": "Llama 3.3 70B", "context": "128k", "speed": "fastest"},
    {"id": "llama-3.1-8b", "name": "Llama 3.1 8B", "context": "128k", "speed": "fastest"},
]

AVAILABLE_SAMBANOVA_MODELS: list[dict[str, str]] = [
    {"id": "Meta-Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fastest"},
    {"id": "DeepSeek-V3-0324", "name": "DeepSeek V3", "context": "64k", "speed": "fast"},
]

AVAILABLE_HYPERBOLIC_MODELS: list[dict[str, str]] = [
    {"id": "meta-llama/Meta-Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fast"},
    {"id": "deepseek-ai/DeepSeek-R1", "name": "DeepSeek R1", "context": "64k", "speed": "medium"},
]

AVAILABLE_NEBIUS_MODELS: list[dict[str, str]] = [
    {"id": "meta-llama/Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fast"},
    {"id": "Qwen/Qwen-72B-Instruct", "name": "Qwen 72B", "context": "128k", "speed": "medium"},
]

AVAILABLE_SILICONFLOW_MODELS: list[dict[str, str]] = [
    {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen 2.5 72B", "context": "128k", "speed": "fast"},
    {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek V3", "context": "64k", "speed": "fast"},
    {"id": "meta-llama/Meta-Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fast"},
]

AVAILABLE_NVIDIA_NIM_MODELS: list[dict[str, str]] = [
    {"id": "nvidia/llama-3.3-nemotron-super-49b-v1", "name": "Nemotron Super 49B", "context": "128k", "speed": "fast"},
    {"id": "meta/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "medium"},
]

AVAILABLE_LEPTON_MODELS: list[dict[str, str]] = [
    {"id": "meta-llama/Llama-3.3-70B-Instruct", "name": "Llama 3.3 70B", "context": "128k", "speed": "fast"},
]

# --- Aggregator ---
AVAILABLE_OPENROUTER_MODELS: list[dict[str, str]] = [
    {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4 (OpenRouter)", "context": "200k", "speed": "medium"},
    {"id": "openai/gpt-4o", "name": "GPT-4o (OpenRouter)", "context": "128k", "speed": "fast"},
    {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash (OpenRouter)", "context": "1M", "speed": "fastest"},
    {
        "id": "meta-llama/llama-3.3-70b-instruct:free",
        "name": "Llama 3.3 70B (free)",
        "context": "128k",
        "speed": "fast",
    },
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3 (OpenRouter)", "context": "64k", "speed": "fast"},
    {"id": "mistralai/mistral-large", "name": "Mistral Large (OpenRouter)", "context": "128k", "speed": "medium"},
]

# --- Çin providerları ---
AVAILABLE_MOONSHOT_MODELS: list[dict[str, str]] = [
    {"id": "kimi-latest", "name": "Kimi Latest", "context": "128k", "speed": "fast"},
    {"id": "moonshot-v1-128k", "name": "Moonshot 128K", "context": "128k", "speed": "medium"},
    {"id": "moonshot-v1-32k", "name": "Moonshot 32K", "context": "32k", "speed": "fast"},
    {"id": "moonshot-v1-8k", "name": "Moonshot 8K", "context": "8k", "speed": "fastest"},
]

AVAILABLE_ZHIPU_MODELS: list[dict[str, str]] = [
    {"id": "glm-5", "name": "GLM-5", "context": "256k", "speed": "fast"},
    {"id": "glm-4-plus", "name": "GLM-4 Plus", "context": "128k", "speed": "medium"},
    {"id": "glm-4-0520", "name": "GLM-4 (0520)", "context": "128k", "speed": "medium"},
    {"id": "glm-4", "name": "GLM-4", "context": "128k", "speed": "medium"},
    {"id": "glm-4-air", "name": "GLM-4 Air", "context": "128k", "speed": "fastest"},
    {"id": "glm-4-flash", "name": "GLM-4 Flash", "context": "128k", "speed": "fastest"},
    {"id": "glm-zero-preview", "name": "GLM Zero Preview", "context": "128k", "speed": "medium"},
]

AVAILABLE_MINIMAX_MODELS: list[dict[str, str]] = [
    {"id": "MiniMax-Text-01", "name": "MiniMax Text 01", "context": "4M", "speed": "medium"},
    {"id": "abab6.5s-chat", "name": "Abab 6.5S", "context": "32k", "speed": "fast"},
]

AVAILABLE_QWEN_MODELS: list[dict[str, str]] = [
    {"id": "qwen-max", "name": "Qwen Max", "context": "32k", "speed": "medium"},
    {"id": "qwen-plus", "name": "Qwen Plus", "context": "128k", "speed": "fast"},
    {"id": "qwen-turbo", "name": "Qwen Turbo", "context": "128k", "speed": "fastest"},
    {"id": "qwen-long", "name": "Qwen Long", "context": "10M", "speed": "medium"},
]

AVAILABLE_STEPFUN_MODELS: list[dict[str, str]] = [
    {"id": "step-2-16k", "name": "Step 2 16K", "context": "16k", "speed": "fast"},
    {"id": "step-1-8k", "name": "Step 1 8K", "context": "8k", "speed": "fastest"},
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

# --- Tüm provider'ları birleştir ---
AVAILABLE_PROVIDERS: dict[str, list[dict[str, str]]] = {
    "gemini": AVAILABLE_GEMINI_MODELS,
    "openai": AVAILABLE_OPENAI_MODELS,
    "anthropic": AVAILABLE_ANTHROPIC_MODELS,
    "xai": AVAILABLE_XAI_MODELS,
    "deepseek": AVAILABLE_DEEPSEEK_MODELS,
    "mistral": AVAILABLE_MISTRAL_MODELS,
    "cohere": AVAILABLE_COHERE_MODELS,
    "ai21": AVAILABLE_AI21_MODELS,
    "groq": AVAILABLE_GROQ_MODELS,
    "perplexity": AVAILABLE_PERPLEXITY_MODELS,
    "reka": AVAILABLE_REKA_MODELS,
    "writer": AVAILABLE_WRITER_MODELS,
    "fireworks": AVAILABLE_FIREWORKS_MODELS,
    "together": AVAILABLE_TOGETHER_MODELS,
    "deepinfra": AVAILABLE_DEEPINFRA_MODELS,
    "novita": AVAILABLE_NOVITA_MODELS,
    "cerebras": AVAILABLE_CEREBRAS_MODELS,
    "sambanova": AVAILABLE_SAMBANOVA_MODELS,
    "hyperbolic": AVAILABLE_HYPERBOLIC_MODELS,
    "nebius": AVAILABLE_NEBIUS_MODELS,
    "siliconflow": AVAILABLE_SILICONFLOW_MODELS,
    "nvidia": AVAILABLE_NVIDIA_NIM_MODELS,
    "lepton": AVAILABLE_LEPTON_MODELS,
    "openrouter": AVAILABLE_OPENROUTER_MODELS,
    "moonshot": AVAILABLE_MOONSHOT_MODELS,
    "zhipu": AVAILABLE_ZHIPU_MODELS,
    "minimax": AVAILABLE_MINIMAX_MODELS,
    "qwen": AVAILABLE_QWEN_MODELS,
    "stepfun": AVAILABLE_STEPFUN_MODELS,
    "ollama": AVAILABLE_OLLAMA_MODELS,
}

# OpenAI-uyumlu provider'larin base URL'leri
OPENAI_COMPATIBLE_PROVIDERS: dict[str, str] = {
    "xai": "https://api.x.ai/v1",
    "cohere": "https://api.cohere.com/v2",
    "ai21": "https://api.ai21.com/studio/v1",
    "perplexity": "https://api.perplexity.ai",
    "reka": "https://api.reka.ai/v1",
    "writer": "https://api.writer.com/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "together": "https://api.together.xyz/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
    "novita": "https://api.novita.ai/v3/openai",
    "cerebras": "https://api.cerebras.ai/v1",
    "sambanova": "https://api.sambanova.ai/v1",
    "hyperbolic": "https://api.hyperbolic.xyz/v1",
    "nebius": "https://api.studio.nebius.com/v1",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "lepton": "https://api.lepton.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "minimax": "https://api.minimax.chat/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "stepfun": "https://api.stepfun.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


class Settings(BaseSettings):
    """Application-wide configuration."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    llm_provider: str = "gemini"
    llm_fallback_order: str = "groq,gemini,openai,deepseek"

    # Google Gemini
    google_api_key: str = ""
    google_api_key_2: str = ""
    google_api_key_3: str = ""
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
    openai_base_url: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-3-5"

    # xAI
    xai_api_key: str = ""
    xai_model: str = "grok-3-mini"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # Mistral
    mistral_api_key: str = ""
    mistral_model: str = "mistral-small-latest"

    # Cohere
    cohere_api_key: str = ""
    cohere_model: str = "command-r"

    # AI21
    ai21_api_key: str = ""
    ai21_model: str = "jamba-1.5-mini"

    # Perplexity
    perplexity_api_key: str = ""
    perplexity_model: str = "sonar"

    # Reka
    reka_api_key: str = ""
    reka_model: str = "reka-flash"

    # Writer
    writer_api_key: str = ""
    writer_model: str = "palmyra-x-004"

    # OpenAI-uyumlu hızlı inference
    fireworks_api_key: str = ""
    fireworks_model: str = "accounts/fireworks/models/llama-v3p3-70b-instruct"
    together_api_key: str = ""
    together_model: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    deepinfra_api_key: str = ""
    deepinfra_model: str = "meta-llama/Meta-Llama-3.3-70B-Instruct"
    novita_api_key: str = ""
    novita_model: str = "meta-llama/llama-3.3-70b-instruct"
    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"
    sambanova_api_key: str = ""
    sambanova_model: str = "Meta-Llama-3.3-70B-Instruct"
    hyperbolic_api_key: str = ""
    hyperbolic_model: str = "meta-llama/Meta-Llama-3.3-70B-Instruct"
    nebius_api_key: str = ""
    nebius_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    siliconflow_api_key: str = ""
    siliconflow_model: str = "Qwen/Qwen2.5-72B-Instruct"
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1"
    lepton_api_key: str = ""
    lepton_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # Aggregator
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    # Çin providerları
    moonshot_api_key: str = ""
    moonshot_model: str = "moonshot-v1-128k"
    zhipu_api_key: str = ""
    zhipu_model: str = "glm-4-flash"
    minimax_api_key: str = ""
    minimax_model: str = "MiniMax-Text-01"
    qwen_api_key: str = ""
    qwen_model: str = "qwen-plus"
    stepfun_api_key: str = ""
    stepfun_model: str = "step-2-16k"

    # LLM genel
    llm_temperature: float = 0.2
    llm_max_output_tokens: int = 4096

    # --- Yerel LLM ---
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.2"

    # --- Hybrid fallback ---
    hybrid_fallback_enabled: bool = True
    hybrid_fallback_max_steps: int = 4

    # --- Rate Limiting ---
    llm_semaphore_limit: int = 3

    # --- Recovery ---
    recovery_max_attempts: int = 2

    # --- Memory ---
    short_term_max_messages: int = 50
    long_term_n_results: int = 6

    @property
    def groq_api_keys(self) -> list[str]:
        keys = [k for k in (self.groq_api_key_1, self.groq_api_key_2, self.groq_api_key_3) if k.strip()]
        if not keys and self.groq_api_key.strip():
            keys = [self.groq_api_key.strip()]
        return keys

    @property
    def groq_model_chain(self) -> list[str]:
        explicit = [
            self.groq_primary_model.strip(),
            self.groq_fallback_model_1.strip(),
            self.groq_fallback_model_2.strip(),
        ]
        chain = [m for m in explicit if m]
        if not chain and self.groq_llm_model.strip():
            chain.append(self.groq_llm_model.strip())
        legacy = [m.strip() for m in self.groq_fallback_models.split(",") if m.strip()]
        for m in legacy:
            if m not in chain:
                chain.append(m)
        return chain or ["openai/gpt-oss-20b"]

    @property
    def google_api_keys(self) -> list[str]:
        keys = [k.strip() for k in (self.google_api_key, self.google_api_key_2, self.google_api_key_3)]
        return [k for k in keys if k] or [""]

    @property
    def provider_preference(self) -> list[str]:
        primary = (self.llm_provider or "").strip().lower() or "gemini"
        fallback_tokens = [t.strip().lower() for t in self.llm_fallback_order.split(",") if t.strip()]
        supported = list(AVAILABLE_PROVIDERS.keys())
        ordered: list[str] = []
        for c in [primary, *fallback_tokens, *supported]:
            if c in supported and c not in ordered:
                ordered.append(c)
        return ordered

    @property
    def provider_availability(self) -> dict[str, bool]:
        return {
            "gemini": any(k.strip() for k in self.google_api_keys),
            "openai": bool(self.openai_api_key.strip()),
            "anthropic": bool(self.anthropic_api_key.strip()),
            "xai": bool(self.xai_api_key.strip()),
            "deepseek": bool(self.deepseek_api_key.strip()),
            "mistral": bool(self.mistral_api_key.strip()),
            "cohere": bool(self.cohere_api_key.strip()),
            "ai21": bool(self.ai21_api_key.strip()),
            "groq": any(k.strip() for k in self.groq_api_keys),
            "fireworks": bool(self.fireworks_api_key.strip()),
            "together": bool(self.together_api_key.strip()),
            "deepinfra": bool(self.deepinfra_api_key.strip()),
            "novita": bool(self.novita_api_key.strip()),
            "cerebras": bool(self.cerebras_api_key.strip()),
            "sambanova": bool(self.sambanova_api_key.strip()),
            "hyperbolic": bool(self.hyperbolic_api_key.strip()),
            "nebius": bool(self.nebius_api_key.strip()),
            "siliconflow": bool(self.siliconflow_api_key.strip()),
            "nvidia": bool(self.nvidia_api_key.strip()),
            "lepton": bool(self.lepton_api_key.strip()),
            "openrouter": bool(self.openrouter_api_key.strip()),
            "moonshot": bool(self.moonshot_api_key.strip()),
            "zhipu": bool(self.zhipu_api_key.strip()),
            "minimax": bool(self.minimax_api_key.strip()),
            "qwen": bool(self.qwen_api_key.strip()),
            "stepfun": bool(self.stepfun_api_key.strip()),
            "perplexity": bool(self.perplexity_api_key.strip()),
            "reka": bool(self.reka_api_key.strip()),
            "writer": bool(self.writer_api_key.strip()),
            "ollama": self.ollama_enabled,
        }

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_allowed_users: str = ""

    @property
    def allowed_user_ids(self) -> list[int]:
        if not self.telegram_allowed_users.strip():
            return []
        return [int(uid.strip()) for uid in self.telegram_allowed_users.split(",") if uid.strip()]

    # --- Guardian ---
    hitl_timeout_minutes: int = 5
    approval_mode: str = "ask"

    # --- Paths ---
    chroma_persist_dir: Path = Path("./data/chromadb")
    sqlite_db_path: Path = Path("./data/omnicore.db")

    # --- Logging ---
    log_level: str = "INFO"

    # --- Scheduler ---
    scheduler_enabled: bool = True
    scheduler_db_path: Path = Path("./data/apscheduler.db")

    # --- REST API ---
    rest_api_key: str = ""

    # --- Personalization ---
    user_name: str = ""
    system_name: str = "OmniCore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def invalidate_settings_cache() -> None:
    get_settings.cache_clear()


def get_available_models(provider: str | None = None) -> dict[str, list[dict[str, str]]]:
    if provider is None:
        return dict(AVAILABLE_PROVIDERS)
    normalized = (provider or "").strip().lower()
    if normalized in AVAILABLE_PROVIDERS:
        return {normalized: AVAILABLE_PROVIDERS[normalized]}
    return {}
