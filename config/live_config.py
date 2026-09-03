"""Live configuration manager — runtime overrides persisted directly to .env.

Tum ayarlar tek dosyada: .env
Degisiklikler aninda uygulanir VE .env dosyasina kalici olarak kaydedilir.
Ayri .env.local dosyasina ihtiyac yoktur.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from config.logging import get_logger

logger = get_logger(__name__)


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
_ENV_FILE = _PROJECT_ROOT / ".env"

# Tüm ayar anahtarları: schema key -> env var, tip, açıklama
CONFIG_SCHEMA: dict[str, dict[str, Any]] = {
    "model": {
        "env_var": "OMNI_LLM_MODEL",
        "type": str,
        "description": "Aktif model (provider'a göre değişir)",
    },
    "provider": {
        "env_var": "LLM_PROVIDER",
        "type": str,
        "description": "Aktif LLM provider",
    },
    "name": {
        "env_var": "USER_NAME",
        "type": str,
        "description": "Görünén ad",
    },
    "temperature": {
        "env_var": "LLM_TEMPERATURE",
        "type": float,
        "description": "LLM sıcaklık değeri (0.0-2.0)",
        "min": 0.0,
        "max": 2.0,
    },
    "max_tokens": {
        "env_var": "LLM_MAX_OUTPUT_TOKENS",
        "type": int,
        "description": "Maksimum output token sayısı",
        "min": 256,
        "max": 1000000,
    },
    "approval_mode": {
        "env_var": "APPROVAL_MODE",
        "type": str,
        "description": "Onay modu: full/safe/ask",
    },
    "groq_model": {
        "env_var": "GROQ_PRIMARY_MODEL",
        "type": str,
        "description": "Aktif Groq modeli",
    },
    "gemini_model": {
        "env_var": "OMNI_LLM_MODEL",
        "type": str,
        "description": "Aktif Gemini modeli",
    },
    "log_level": {
        "env_var": "LOG_LEVEL",
        "type": str,
        "description": "Log seviyesi (DEBUG/INFO/WARNING/ERROR)",
    },
    "scheduler": {
        "env_var": "SCHEDULER_ENABLED",
        "type": bool,
        "description": "Zamanlayıcı aç/kapat",
    },
    "hybrid_fallback": {
        "env_var": "HYBRID_FALLBACK_ENABLED",
        "type": bool,
        "description": "Hybrid fallback aç/kapat",
    },
    "hitl_timeout": {
        "env_var": "HITL_TIMEOUT_MINUTES",
        "type": int,
        "description": "Onay zaman aşımı (dakika)",
        "min": 1,
        "max": 60,
    },
    "fallback_order": {
        "env_var": "LLM_FALLBACK_ORDER",
        "type": str,
        "description": "Provider fallback sırası",
    },
    "short_term_memory": {
        "env_var": "SHORT_TERM_MAX_MESSAGES",
        "type": int,
        "description": "Kısa vadeli bellek kapasitesi",
        "min": 10,
        "max": 500,
    },
    "long_term_results": {
        "env_var": "LONG_TERM_N_RESULTS",
        "type": int,
        "description": "Uzun vadeli bellek sonuç sayısı",
        "min": 1,
        "max": 20,
    },
}

# Model kısa isimleri: alias -> gerçek model ID
MODEL_ALIASES: dict[str, dict[str, str]] = {
    "gemini": {
        "flash": "gemini-2.5-flash",
        "lite": "gemini-2.5-flash-lite",
        "pro": "gemini-2.5-pro",
    },
    "openai": {
        "4o": "gpt-4o",
        "4o-mini": "gpt-4o-mini",
        "4.1": "gpt-4.1",
        "4.1-mini": "gpt-4.1-mini",
        "o3": "o3-mini",
        "o4": "o4-mini",
    },
    "anthropic": {
        "opus": "claude-opus-4-5",
        "sonnet": "claude-sonnet-4-5",
        "haiku": "claude-haiku-3-5",
    },
    "groq": {
        "20b": "openai/gpt-oss-20b",
        "120b": "openai/gpt-oss-120b",
        "mixtral": "mixtral-8x7b-32768",
        "gemma": "gemma2-9b-it",
        "llama70b": "llama-3.3-70b-versatile",
        "llama8b": "llama-3.1-8b-instant",
        "deepseek": "deepseek-r1-distill-llama-70b",
        "qwen": "qwen-qwq-32b",
        "scout": "meta-llama/llama-4-scout-17b-16e-instruct",
    },
    "xai": {
        "grok3": "grok-3",
        "grok": "grok-3-mini",
    },
    "deepseek": {
        "chat": "deepseek-chat",
        "r1": "deepseek-reasoner",
    },
    "mistral": {
        "large": "mistral-large-latest",
        "small": "mistral-small-latest",
        "codex": "codestral-latest",
    },
    "cohere": {
        "r+": "command-r-plus",
        "r": "command-r",
    },
    "qwen": {
        "max": "qwen-max",
        "plus": "qwen-plus",
        "turbo": "qwen-turbo",
        "long": "qwen-long",
    },
    "ollama": {
        "llama": "llama3.2",
        "mistral": "mistral",
        "gemma": "gemma2",
        "qwen": "qwen2.5",
        "phi": "phi4",
        "r1": "deepseek-r1",
    },
}


def _read_env() -> dict[str, str]:
    """Read key=value pairs from .env."""
    result: dict[str, str] = {}
    if not _ENV_FILE.exists():
        return result
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip("\"'")
    return result


def _write_env(data: dict[str, str]) -> None:
    """Write key=value pairs to .env, preserving comments."""
    # Read existing .env to preserve comments
    original_lines: list[str] = []
    if _ENV_FILE.exists():
        original_lines = _ENV_FILE.read_text(encoding="utf-8").splitlines()

    # Rebuild file: keep comments/structure, update values
    output_lines: list[str] = []
    updated_keys: set[str] = set()

    for line in original_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in data:
                value = data[key]
                if " " in value or "#" in value:
                    output_lines.append(f'{key}="{value}"')
                else:
                    output_lines.append(f"{key}={value}")
                updated_keys.add(key)
            else:
                output_lines.append(line)
        else:
            output_lines.append(line)

    # Append any new keys not in original file
    for key in sorted(data.keys()):
        if key not in updated_keys:
            value = data[key]
            if " " in value or "#" in value:
                output_lines.append(f'{key}="{value}"')
            else:
                output_lines.append(f"{key}={value}")

    _ENV_FILE.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def resolve_model_alias(value: str, provider: str | None = None) -> str:
    """Resolve short model aliases to full model IDs."""
    value_lower = value.lower().strip()
    if provider and provider in MODEL_ALIASES:
        resolved = MODEL_ALIASES[provider].get(value_lower)
        if resolved:
            return resolved
    for prov_aliases in MODEL_ALIASES.values():
        resolved = prov_aliases.get(value_lower)
        if resolved:
            return resolved
    return value


class LiveConfig:
    """Tek dosya tabanlı runtime konfigürasyon.

    Oku: env vars -> .env
    Yaz: .env (doğrudan)
    """

    def __init__(self) -> None:
        self._overrides: dict[str, str] = _read_env()
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        """Override'ları process environment'a uygula."""
        for key, value in self._overrides.items():
            os.environ[key] = value

    def get(self, key: str) -> str | None:
        """Schema key ile değer al (örneğin 'model', 'provider')."""
        if key == "approval_mode":
            return self._overrides.get("APPROVAL_MODE") or os.environ.get("APPROVAL_MODE", "ask")
        schema = CONFIG_SCHEMA.get(key)
        if not schema:
            return None
        env_var = schema["env_var"]
        if not env_var:
            return None
        return self._overrides.get(env_var) or os.environ.get(env_var, "")

    def set(self, key: str, value: str) -> tuple[bool, str]:
        """Ayar değeri ata. (başarı, mesaj) döner."""
        schema = CONFIG_SCHEMA.get(key)
        if not schema:
            valid_keys = ", ".join(CONFIG_SCHEMA.keys())
            return False, f"Geçersiz anahtar: {key}\nGeçerli anahtarlar: {valid_keys}"

        # Tip doğrulama ve normalizasyon
        try:
            if key == "approval_mode":
                norm = value.lower().strip()
                if norm in ("full", "yes", "tam", "all", "true"):
                    typed_value = "yes"
                elif norm in ("safe", "guvenli"):
                    typed_value = "safe"
                else:
                    typed_value = "ask"
            elif schema["type"] is bool:
                normalized = value.lower().strip()
                if normalized in ("true", "1", "yes", "evet", "ac", "on"):
                    typed_value = "true"
                elif normalized in ("false", "0", "no", "hayir", "kapat", "off"):
                    typed_value = "false"
                else:
                    return False, f"Geçersiz değer (true/false): {value}"
            elif schema["type"] is int:
                typed_value = str(int(value))
                min_val = schema.get("min")
                max_val = schema.get("max")
                int_val = int(typed_value)
                if min_val is not None and int_val < min_val:
                    return False, f"Değer çok düşük: {int_val} (min: {min_val})"
                if max_val is not None and int_val > max_val:
                    return False, f"Değer çok yüksek: {int_val} (max: {max_val})"
            elif schema["type"] is float:
                typed_value = str(float(value))
                min_val = schema.get("min")
                max_val = schema.get("max")
                float_val = float(typed_value)
                if min_val is not None and float_val < min_val:
                    return False, f"Değer çok düşük: {float_val} (min: {min_val})"
                if max_val is not None and float_val > max_val:
                    return False, f"Değer çok yüksek: {float_val} (max: {max_val})"
            else:
                typed_value = value.strip()
        except (ValueError, TypeError) as exc:
            return False, f"Geçersiz değer tipi: {exc}"

        env_var = schema["env_var"]
        if not env_var:
            return True, f"✅ {key} = {typed_value} (sadece runtime)"

        # Kaydet
        self._overrides[env_var] = typed_value
        os.environ[env_var] = typed_value

        # Model değiştirilirse provider'a göre ilgili değişkeni de güncelle
        if key == "model":
            active_p = self._overrides.get("LLM_PROVIDER") or os.environ.get("LLM_PROVIDER", "gemini")
            if active_p == "groq" or "/" in typed_value or "llama" in typed_value.lower():
                self._overrides["GROQ_PRIMARY_MODEL"] = typed_value
                self._overrides["GROQ_LLM_MODEL"] = typed_value
                os.environ["GROQ_PRIMARY_MODEL"] = typed_value
                os.environ["GROQ_LLM_MODEL"] = typed_value
            elif active_p == "gemini":
                self._overrides["OMNI_LLM_MODEL"] = typed_value
                os.environ["OMNI_LLM_MODEL"] = typed_value

        _write_env(self._overrides)

        try:
            from config.settings import invalidate_settings_cache
            invalidate_settings_cache()
        except Exception:
            pass

        logger.info("config.updated", key=key, env_var=env_var, value=typed_value)
        return True, f"✅ {key} = {typed_value}"

    def set_model_for_provider(self, provider: str, model_id: str) -> tuple[bool, str]:
        """Belirli bir provider için model ata ve .env'ye kaydet."""
        p = provider.lower().strip()
        var_map = {
            "gemini": "OMNI_LLM_MODEL",
            "groq": "GROQ_PRIMARY_MODEL",
            "openai": "OPENAI_MODEL",
            "anthropic": "ANTHROPIC_MODEL",
            "deepseek": "DEEPSEEK_MODEL",
            "mistral": "MISTRAL_MODEL",
            "ollama": "OLLAMA_MODEL",
        }
        target_var = var_map.get(p, "OMNI_LLM_MODEL")
        self._overrides[target_var] = model_id
        os.environ[target_var] = model_id
        if p == "groq":
            self._overrides["GROQ_LLM_MODEL"] = model_id
            os.environ["GROQ_LLM_MODEL"] = model_id
        elif p == "gemini":
            self._overrides["OMNI_LLM_MODEL"] = model_id
            os.environ["OMNI_LLM_MODEL"] = model_id
        _write_env(self._overrides)

        try:
            from config.settings import invalidate_settings_cache
            invalidate_settings_cache()
        except Exception:
            pass

        logger.info("config.provider_model_updated", provider=p, var=target_var, model=model_id)
        return True, f"✅ {p.capitalize()} modeli '{model_id}' olarak güncellendi."

    def show(self) -> str:
        """Tüm ayarları göster."""
        lines = ["⚙️  Yapılandırma Ayarları:\n"]
        for key, schema in CONFIG_SCHEMA.items():
            env_var = schema.get("env_var")
            if not env_var:
                continue
            current = self._overrides.get(env_var) or os.environ.get(env_var, "(varsayılan)")
            desc = schema["description"]
            lines.append(f"  {key:<20} = {current:<25} # {desc}")
        lines.append(
            "\n💡 Değiştirmek için: /config set <anahtar> <değer>\n"
            "💡 Değeri görmek için: /config get <anahtar>"
        )
        return "\n".join(lines)

    def get_env_value(self, env_var: str) -> str | None:
        """Ham environment variable değeri al."""
        return self._overrides.get(env_var) or os.environ.get(env_var)


# Singleton
_live_config: LiveConfig | None = None


def get_live_config() -> LiveConfig:
    """LiveConfig singleton'ini al veya oluştur."""
    global _live_config
    if _live_config is None:
        _live_config = LiveConfig()
    return _live_config
