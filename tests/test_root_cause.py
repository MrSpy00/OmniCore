"""Unit tests for RootCauseAnalyzer error classification and recovery suggestions."""

from __future__ import annotations

import pytest

from core.root_cause import RootCauseAnalyzer


class TestRootCauseClassification:
    """Verify that error messages are mapped to the correct root causes."""

    @pytest.mark.parametrize(
        ("error_msg", "expected_category"),
        [
            ("Permission denied: cannot write to /etc/hosts", "permission"),
            ("Access denied: elevated privileges required", "permission"),
            ("Connection timed out after 30 seconds", "timeout"),
            ("Deadline exceeded waiting for response", "timeout"),
            ("File not found: /var/log/app.log", "not_found"),
            ("Hedef dosya bulunamadı", "not_found"),
            ("No such file or directory: 'config.json'", "not_found"),
            ("ModuleNotFoundError: No module named 'scipy'", "dependency"),
            ("Package not found: pyyaml is not installed", "dependency"),
            ("Connection refused by peer", "network"),
            ("DNS getaddrinfo failed to resolve host", "network"),
            ("HTTP 429 Too Many Requests: quota exceeded", "rate_limit"),
            ("API throttled due to rate limits", "rate_limit"),
            ("JSONDecodeError: Expecting ',' delimiter at line 1", "data_format"),
            ("Malformed payload: invalid token encountered", "data_format"),
            ("HTTP 401 Unauthorized: Invalid API key", "auth"),
            ("Authentication token expired", "auth"),
            ("No space left on device: /tmp", "disk"),
            ("Disk full: insufficient disk space", "disk"),
            ("Database deadlock detected while acquiring lock", "concurrency"),
            ("Resource is already locked by another process", "concurrency"),
            ("An unexpected mystery happened", "unknown"),
        ],
    )
    def test_classify_categories(self, error_msg: str, expected_category: str):
        assert RootCauseAnalyzer.classify(error_msg) == expected_category

    def test_classify_case_insensitivity(self):
        assert RootCauseAnalyzer.classify("ACCESS DENIED: ADMIN REQUIRED") == "permission"
        assert RootCauseAnalyzer.classify("TiMeOuT occurred") == "timeout"


class TestRootCauseSuggestionsAndAnalysis:
    """Verify recovery suggestions and comprehensive analysis output."""

    def test_suggest_recovery_with_supported_category(self):
        tool, params = RootCauseAnalyzer.suggest_recovery("permission", "execute_shell")
        assert tool == "terminal_execute"
        assert "RunAs" in params.get("command", "")

    def test_suggest_recovery_with_not_found(self):
        tool, params = RootCauseAnalyzer.suggest_recovery("not_found", "os_read_file")
        assert tool == "os_list_directory"
        assert params.get("path") == "."

    def test_suggest_recovery_empty_category(self):
        tool, params = RootCauseAnalyzer.suggest_recovery("rate_limit", "llm_call")
        assert tool == ""
        assert params == {}

    def test_suggest_recovery_unknown_category(self):
        tool, params = RootCauseAnalyzer.suggest_recovery("unknown", "some_tool")
        assert tool == ""
        assert params == {}

    def test_analyze_with_recovery(self):
        result = RootCauseAnalyzer.analyze(
            error_message="Permission denied opening /system/root",
            failed_tool="os_read_file",
        )
        assert result["root_cause"] == "permission"
        assert result["error_message"] == "Permission denied opening /system/root"
        assert result["failed_tool"] == "os_read_file"
        assert result["recovery_tool"] == "terminal_execute"
        assert result["has_recovery"] is True

    def test_analyze_without_recovery(self):
        result = RootCauseAnalyzer.analyze(
            error_message="Rate limit 429: Too many requests",
            failed_tool="api_query",
        )
        assert result["root_cause"] == "rate_limit"
        assert result["has_recovery"] is False
        assert result["recovery_tool"] == ""
