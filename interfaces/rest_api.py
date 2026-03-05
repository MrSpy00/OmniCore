"""REST API gateway using FastAPI.

Provides an HTTP interface for webhooks, external integrations, and
potential future mobile/web frontends.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from config.logging import get_logger
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)


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
        from fastapi import FastAPI, HTTPException
    except ImportError:
        raise ImportError(
            "FastAPI is required for the REST gateway. Install it with: uv add fastapi uvicorn"
        )

    app = FastAPI(
        title="OmniCore API",
        version="0.1.0",
        description="HTTP gateway for the OmniCore AI assistant.",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        msg = Message(
            role=MessageRole.USER,
            content=req.message,
            channel="rest",
            user_id=req.user_id,
        )
        try:
            reply = await router.handle_message(msg, req.conversation_id)
            return ChatResponse(reply=reply, conversation_id=req.conversation_id)
        except Exception as exc:
            logger.error("rest.chat_error", error=str(exc))
            raise HTTPException(status_code=500, detail=str(exc))

    return app
