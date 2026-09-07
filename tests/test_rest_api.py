"""Unit tests for OmniCore REST API endpoints and authentication."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from config.settings import Settings
from interfaces.rest_api import (
    _check_ip_rate_limit,
    _check_rate_limit,
    _RateLimitError,
    create_rest_app,
)


class TestRestApiHealth:
    """Test /health endpoint metadata, status, and uptime."""

    def test_health_endpoint_success(self):
        settings = Settings(rest_api_key="test-key-123")
        mock_router = MagicMock()
        mock_router._registry = ["tool1", "tool2", "tool3"]

        app = create_rest_app(router=mock_router, settings=settings)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["router_ready"] is True
        assert data["tools_registered"] == 3
        assert data["uptime_seconds"] >= 0
        assert "timestamp" in data

    def test_health_endpoint_no_router(self):
        settings = Settings(rest_api_key="test-key-123")
        app = create_rest_app(router=None, settings=settings)
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["router_ready"] is False
        assert data["tools_registered"] == 0


class TestRestApiAuth:
    """Test Bearer token authentication on protected endpoints."""

    def test_missing_bearer_token_returns_401(self):
        settings = Settings(rest_api_key="secret-token-xyz")
        app = create_rest_app(router=MagicMock(), settings=settings)
        client = TestClient(app)

        response = client.post("/chat", json={"message": "hi", "user_id": "u1"})
        assert response.status_code == 401
        assert "Missing Bearer token" in response.json()["detail"]

    def test_invalid_bearer_token_returns_403(self):
        settings = Settings(rest_api_key="secret-token-xyz")
        app = create_rest_app(router=MagicMock(), settings=settings)
        client = TestClient(app)

        response = client.post(
            "/chat",
            json={"message": "hi", "user_id": "u1"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 403
        assert "Invalid API key" in response.json()["detail"]

    def test_valid_bearer_token_passes_auth(self):
        settings = Settings(rest_api_key="secret-token-xyz")
        mock_router = MagicMock()
        mock_router.handle_message = AsyncMock(return_value="Hello from OmniCore!")

        app = create_rest_app(router=mock_router, settings=settings)
        client = TestClient(app)

        response = client.post(
            "/chat",
            json={"message": "hi", "user_id": "u1"},
            headers={"Authorization": "Bearer secret-token-xyz"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Hello from OmniCore!"


class TestRestApiChat:
    """Test /chat request processing and error handling."""

    def test_chat_success_flow(self):
        settings = Settings(rest_api_key="my-key")
        mock_router = MagicMock()
        mock_router.handle_message = AsyncMock(return_value="Task completed.")

        app = create_rest_app(router=mock_router, settings=settings)
        client = TestClient(app)

        response = client.post(
            "/chat",
            json={"message": "Run report", "user_id": "u1", "conversation_id": "conv-42"},
            headers={"Authorization": "Bearer my-key"},
        )
        assert response.status_code == 200
        assert response.json()["reply"] == "Task completed."
        assert response.json()["conversation_id"] == "conv-42"

    def test_chat_internal_error_returns_500(self):
        settings = Settings(rest_api_key="my-key")
        mock_router = MagicMock()
        mock_router.handle_message = AsyncMock(side_effect=RuntimeError("Router crashed"))

        app = create_rest_app(router=mock_router, settings=settings)
        client = TestClient(app)

        response = client.post(
            "/chat",
            json={"message": "Crash me", "user_id": "u1"},
            headers={"Authorization": "Bearer my-key"},
        )
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


class TestRateLimiting:
    """Test user and IP rate limit functions."""

    def test_rate_limit_exceeded(self):
        test_key = f"test_client_{time.time()}"
        # Trigger 30 calls
        for _ in range(30):
            _check_rate_limit(test_key)

        # 31st call should raise _RateLimitError
        with pytest.raises(_RateLimitError):
            _check_rate_limit(test_key)

    def test_ip_rate_limit_exceeded(self):
        test_ip = f"192.0.2.{int(time.time()) % 250}"
        # Trigger 100 calls
        for _ in range(100):
            _check_ip_rate_limit(test_ip)

        # 101st call should raise _RateLimitError
        with pytest.raises(_RateLimitError):
            _check_ip_rate_limit(test_ip)
