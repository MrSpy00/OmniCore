"""Kök Neden Analizcisi — Hata mesajlarını sınıflandırır ve kurtarma önerisi üretir.

Tool hatalarında "sadece hata aldım" demek yerine hatanın kök nedenini analiz edip
alternatif bir yaklaşım öneren ReAct mekanizmasının temel taşı.
"""

from __future__ import annotations

from typing import Any


class RootCauseAnalyzer:
    """Hata mesajlarını kök nedenlere sınıflandırır ve kurtarma önerisi üretir."""

    ROOT_CAUSES: dict[str, tuple[str, ...]] = {
        "permission": ("access denied", "permission denied", "elevated", "admin", "runas", "not authorized"),
        "timeout": ("timeout", "timed out", "deadline exceeded", "timedout"),
        "not_found": ("not found", "no such file", "does not exist", "bulunamadı", "dosya bulunamadı"),
        "dependency": ("not installed", "module not found", "import error", "no module named", "package not found"),
        "network": ("connection", "dns", "resolve", "refused", "unreachable", "getaddrinfo", "name resolution"),
        "rate_limit": ("429", "rate limit", "quota", "too many requests", "resource_exhausted", "throttl"),
        "data_format": ("json", "parse", "decode", "invalid", "malformed", "unexpected token", "decodeerror"),
        "auth": ("unauthorized", "401", "invalid api key", "authentication", "token expired", "invalid_key"),
        "disk": ("no space left", "disk full", "quota exceeded", "insufficient disk"),
        "concurrency": ("deadlock", "lock", "busy", "concurrent", "already locked"),
    }

    RECOVERY_SUGGESTIONS: dict[str, list[tuple[str, dict[str, Any]]]] = {
        "permission": [
            ("terminal_execute", {
                "command": "Start-Process powershell -Verb RunAs "
                           "-ArgumentList '-Command \"echo elevated\"'"
            }),
        ],
        "timeout": [
            ("terminal_execute", {"command": "echo Timeout detected, retrying with extended timeout"}),
        ],
        "not_found": [
            ("os_list_directory", {"path": "."}),
        ],
        "dependency": [
            ("terminal_execute", {"command": "uv pip install {missing_module}"}),
        ],
        "network": [
            ("network_ping", {"host": "8.8.8.8"}),
        ],
        "rate_limit": [],
        "data_format": [],
        "auth": [],
        "disk": [
            ("system_optimizer_cleanup_temp", {}),
        ],
        "concurrency": [
            ("terminal_execute", {"command": "echo Waiting for resource release..."}),
        ],
    }

    @classmethod
    def classify(cls, error_message: str) -> str:
        """Hata mesajını kök neden kategorisine sınıflandırır."""
        error_lower = error_message.lower()
        for category, keywords in cls.ROOT_CAUSES.items():
            for keyword in keywords:
                if keyword in error_lower:
                    return category
        return "unknown"

    @classmethod
    def suggest_recovery(
        cls, root_cause: str, failed_tool: str
    ) -> tuple[str, dict[str, Any]]:
        """Kök neden ve başarısız araca göre kurtarma eylemi önerir."""
        suggestions = cls.RECOVERY_SUGGESTIONS.get(root_cause, [])
        if suggestions:
            tool_name, params = suggestions[0]
            return tool_name, params
        return "", {}

    @classmethod
    def analyze(cls, error_message: str, failed_tool: str) -> dict[str, Any]:
        """Tam kök neden analizi — sınıflandırma + kurtarma önerisi."""
        root_cause = cls.classify(error_message)
        recovery_tool, recovery_params = cls.suggest_recovery(root_cause, failed_tool)

        return {
            "root_cause": root_cause,
            "error_message": error_message,
            "failed_tool": failed_tool,
            "recovery_tool": recovery_tool,
            "recovery_params": recovery_params,
            "has_recovery": bool(recovery_tool),
        }
