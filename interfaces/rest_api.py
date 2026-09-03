"""REST API gateway using FastAPI.

Provides an HTTP interface for webhooks, external integrations, and
potential future mobile/web frontends.
"""

from __future__ import annotations

import secrets
import time
from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from config.logging import get_logger
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

# --- Rate Limiting (in-memory, per-user) -------------------------------------
_rate_limits: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 20  # max requests per window


def _check_rate_limit(user_id: str) -> None:
    now = time.time()
    _rate_limits[user_id] = [t for t in _rate_limits[user_id] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limits[user_id]) >= _RATE_LIMIT_MAX:
        raise _RateLimitError()
    _rate_limits[user_id].append(now)


class _RateLimitError(Exception):
    pass


class ChatRequest(BaseModel):
    """Incoming chat request payload."""

    message: str
    user_id: str = "api_user"
    conversation_id: str = "api_default"


class ChatResponse(BaseModel):
    """Outgoing chat response payload."""

    reply: str
    conversation_id: str


def create_app(router: CognitiveRouter) -> Any:
    """Create and return a FastAPI application wired to the CognitiveRouter.

    Usage::

        from interfaces.rest_api import create_app
        app = create_app(router)
        # Then run with: uvicorn interfaces.rest_api:app
    """
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
    except ImportError:
        raise ImportError("FastAPI is required for the REST gateway. Install it with: uv add fastapi uvicorn")

    from config.settings import get_settings

    app = FastAPI(
        title="OmniCore API",
        version="0.1.0",
        description="HTTP gateway for the OmniCore AI assistant.",
    )

    async def verify_api_key(authorization: str = Header(default="")):
        settings = get_settings()
        expected = settings.rest_api_key
        if not expected:
            return
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization[7:]
        if not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=403, detail="Invalid API key")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
    async def chat(req: ChatRequest) -> ChatResponse:
        _check_rate_limit(req.user_id)
        msg = Message(
            role=MessageRole.USER,
            content=req.message,
            channel="rest",
            user_id=req.user_id,
        )
        try:
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
