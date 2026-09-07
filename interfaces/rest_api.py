"""REST API gateway using FastAPI.

Provides an HTTP interface for webhooks, external integrations, and
potential future mobile/web frontends.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any

from pydantic import BaseModel, Field

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    pass

from config.logging import get_logger
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

# --- Rate Limiting (in-memory, per-client/user) --------------------------------
# SECURITY: Use TTL-based cache to prevent memory leaks
# Max entries: 10000, TTL: 60 seconds
_rate_limits: dict[str, list[float]] = {}
_ip_rate_limits: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = threading.Lock()
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 30  # max requests per window
_IP_RATE_LIMIT_MAX = 100  # max requests per window per IP
_RATE_LIMIT_CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes
_last_cleanup_time = time.time()


def _cleanup_rate_limits() -> None:
    """Remove expired entries to prevent memory leaks."""
    global _last_cleanup_time
    now = time.time()
    if now - _last_cleanup_time < _RATE_LIMIT_CLEANUP_INTERVAL:
        return

    expired_keys = [
        k for k, timestamps in _rate_limits.items() if not timestamps or now - timestamps[-1] >= _RATE_LIMIT_WINDOW
    ]
    for k in expired_keys:
        _rate_limits.pop(k, None)
    _last_cleanup_time = now


def _check_rate_limit(key: str) -> None:
    global _rate_limits
    now = time.time()

    with _rate_limit_lock:
        # SECURITY: Periodic cleanup to prevent memory leaks
        _cleanup_rate_limits()

        # Get or create entry
        if key not in _rate_limits:
            _rate_limits[key] = []

        # Filter to only valid timestamps within window
        valid_times = [t for t in _rate_limits[key] if now - t < _RATE_LIMIT_WINDOW]

        if len(valid_times) >= _RATE_LIMIT_MAX:
            _rate_limits[key] = valid_times
            raise _RateLimitError()

        valid_times.append(now)
        _rate_limits[key] = valid_times

        # SECURITY: Hard limit on total entries to prevent DoS
        if len(_rate_limits) > 10000:
            # Remove oldest entries
            sorted_keys = sorted(_rate_limits, key=lambda k: _rate_limits[k][-1] if _rate_limits[k] else 0)
            for k in sorted_keys[:1000]:
                _rate_limits.pop(k, None)


def _check_ip_rate_limit(ip: str) -> None:
    now = time.time()
    with _rate_limit_lock:
        valid_times = [t for t in _ip_rate_limits[ip] if now - t < _RATE_LIMIT_WINDOW]
        if len(valid_times) >= _IP_RATE_LIMIT_MAX:
            _ip_rate_limits[ip] = valid_times
            raise _RateLimitError()
        valid_times.append(now)
        _ip_rate_limits[ip] = valid_times
        if len(_ip_rate_limits) > 10000:
            sorted_ips = sorted(
                _ip_rate_limits,
                key=lambda k: _ip_rate_limits[k][-1] if _ip_rate_limits[k] else 0,
            )
            for k in sorted_ips[:1000]:
                _ip_rate_limits.pop(k, None)


class _RateLimitError(Exception):
    pass


class ChatRequest(BaseModel):
    """Incoming chat request payload."""

    message: str = Field(..., min_length=1, max_length=65536)
    user_id: str = Field(default="api_user", max_length=128)
    conversation_id: str = Field(default="api_default", max_length=128)


class ChatResponse(BaseModel):
    """Outgoing chat response payload."""

    reply: str
    conversation_id: str


_EPHEMERAL_KEY: str | None = None


def create_app(router: CognitiveRouter | None = None, settings: Any = None) -> Any:
    """Create and return a FastAPI application wired to the CognitiveRouter."""
    global _EPHEMERAL_KEY
    if "FastAPI" not in globals() or FastAPI is None:
        raise ImportError("FastAPI is required for the REST gateway. Install it with: uv add fastapi uvicorn")

    from config.settings import get_settings

    if settings is None:
        settings = get_settings()
    configured_key = settings.rest_api_key.strip() if settings.rest_api_key else ""
    if not configured_key:
        if _EPHEMERAL_KEY is None:
            _EPHEMERAL_KEY = secrets.token_urlsafe(32)
            # SECURITY: Mask the ephemeral key in logs to prevent unauthorized access
            masked_key = f"{_EPHEMERAL_KEY[:4]}...{_EPHEMERAL_KEY[-4:]}" if len(_EPHEMERAL_KEY) > 8 else "***"
            logger.warning(
                "rest.no_api_key_configured_ephemeral_generated",
                ephemeral_key_masked=masked_key,
                hint="Set REST_API_KEY in .env for persistent access.",
            )
            if os.environ.get("OMNICORE_LOG_EPHEMERAL_KEY", "0").lower() in ("1", "true"):
                logger.info("rest.ephemeral_key", key=_EPHEMERAL_KEY)
        effective_key = _EPHEMERAL_KEY
    else:
        effective_key = configured_key

    try:
        api_version = pkg_version("omnicore")
    except PackageNotFoundError:
        api_version = "0.1.0"

    start_time = time.time()

    app = FastAPI(
        title="OmniCore API",
        version=api_version,
        description="HTTP gateway for the OmniCore AI assistant.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:8080"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    async def verify_api_key(authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization[7:].strip()
        if not secrets.compare_digest(token, effective_key):
            raise HTTPException(status_code=403, detail="Invalid API key")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        tools_count = len(router._registry) if (router is not None and hasattr(router, "_registry")) else 0
        return {
            "status": "ok",
            "version": api_version,
            "uptime_seconds": int(time.time() - start_time),
            "tools_registered": tools_count,
            "router_ready": router is not None,
            "timestamp": time.time(),
        }

    @app.post("/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
    async def chat(req: ChatRequest, request: Request) -> ChatResponse:
        client_ip = request.client.host if request.client else "unknown"
        rate_key = f"{client_ip}:{req.user_id}"

        if router is None:
            raise HTTPException(status_code=503, detail="Router not initialized")

        try:
            # Check both per-user and per-IP rate limits
            _check_rate_limit(rate_key)
            _check_ip_rate_limit(client_ip)
            msg = Message(
                role=MessageRole.USER,
                content=req.message,
                channel="rest",
                user_id=req.user_id,
            )
            reply = await router.handle_message(msg, req.conversation_id)
            return ChatResponse(reply=reply, conversation_id=req.conversation_id)
        except _RateLimitError:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
        except Exception as exc:
            logger.error("rest.chat_error", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail="Internal server error. Check logs for details.",
            )

    return app


create_rest_app = create_app
