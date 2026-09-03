"""Web Dashboard — Modern FastAPI + HTML/CSS/JS frontend for OmniCore.

Launch with: uv run omnicore --mode web
Serves on: http://localhost:8080
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from config.logging import get_logger
from config.settings import get_settings
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

_router: CognitiveRouter | None = None
_start_time: float = time.time()


def set_router(router: CognitiveRouter) -> None:
    global _router
    _router = router


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="OmniCore Dashboard", docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return DASHBOARD_HTML

    @app.get("/favicon.ico")
    async def favicon():
        return Response(content=b"", media_type="image/x-icon")

    @app.get("/api/status")
    async def api_status():
        if not _router:
            return JSONResponse({"error": "Router not ready"}, status_code=503)
        settings = get_settings()
        from config.live_config import get_live_config

        live_config = get_live_config()
        provider = live_config.get("provider") or getattr(_router, "_runtime_provider", "unknown")
        model = live_config.get("model") or (
            settings.omni_llm_model if provider == "gemini" else settings.groq_primary_model
        )
        tools = len(_router._registry) if hasattr(_router, "_registry") else 0
        uptime = int(time.time() - _start_time)
        return {
            "status": "online",
            "provider": provider,
            "model": model,
            "tools": tools,
            "uptime_seconds": uptime,
            "plan_mode": _router._guardian.plan_mode if hasattr(_router, "_guardian") else False,
            "approval_mode": _router._guardian.mode.value if hasattr(_router, "_guardian") else "ask",
        }

    @app.get("/api/chat/stream")
    async def api_chat_stream(message: str = Query(...)):
        text = message.strip()
        if not text:
            return JSONResponse({"error": "Empty message"}, status_code=400)
        if not _router:
            return JSONResponse({"error": "Router not ready"}, status_code=503)

        msg = Message(
            role=MessageRole.USER,
            content=text,
            channel="web",
            user_id="web_user",
        )

        async def event_generator():
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

            async def on_progress(event_type: str, data: dict[str, Any]):
                await queue.put({"type": event_type, "data": data})

            async def run_task():
                try:
                    reply = await _router.handle_message(
                        msg, "web_session", on_progress=on_progress
                    )
                    await queue.put({"type": "done", "reply": reply})
                except Exception as exc:
                    logger.error("dashboard.chat_stream_error", error=str(exc))
                    await queue.put({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
                finally:
                    await queue.put(None)

            asyncio.create_task(run_task())

            while True:
                item = await queue.get()
                if item is None:
                    break
                payload = json.dumps(item, ensure_ascii=False)
                yield f"data: {payload}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/chat")
    async def api_chat(request: Request):
        body = await request.json()
        text = body.get("message", "").strip()
        if not text:
            return JSONResponse({"error": "Empty message"}, status_code=400)
        if not _router:
            return JSONResponse({"error": "Router not ready"}, status_code=503)

        msg = Message(
            role=MessageRole.USER,
            content=text,
            channel="web",
            user_id="web_user",
        )
        try:
            reply = await _router.handle_message(msg, "web_session")
            return {"reply": reply, "status": "ok"}
        except Exception as exc:
            logger.error("dashboard.chat_error", error=str(exc))
            return {"reply": f"Hata: {type(exc).__name__}: {exc}", "status": "error"}

    @app.get("/api/models")
    async def api_models():
        from config.settings import get_available_models

        return get_available_models()

    @app.get("/api/tools")
    async def api_tools():
        if not _router or not hasattr(_router, "_registry"):
            return []
        try:
            return _router._registry.list_tools()
        except Exception:
            return []

    @app.post("/api/config")
    async def api_config(request: Request):
        body = await request.json()
        from config.live_config import get_live_config

        lc = get_live_config()
        key = body.get("key", "")
        value = body.get("value", "")
        if key and value:
            ok, msg = lc.set(key, value)
            return {"success": ok, "message": msg}
        return JSONResponse({"error": "Missing key/value"}, status_code=400)

    @app.get("/api/sysinfo")
    @app.get("/api/telemetry")
    async def api_sysinfo():
        import psutil

        cpu = psutil.cpu_percent(interval=0.05)
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": cpu,
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "privacy": "100% Yerel / Local Hardware System Info. Disari veri iletilmez.",
        }


    return app


# Premium Cyber-Obsidian UI - Zero AI Slop, Inline SVGs, Bilingual TR/EN, Glassmorphism
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniCore — Sovereign Autonomous AI OS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg-base: #07090E;
  --bg-card: rgba(15, 19, 30, 0.75);
  --bg-card-hover: rgba(22, 28, 44, 0.85);
  --bg-glass: rgba(11, 15, 24, 0.65);
  --border: rgba(255, 255, 255, 0.08);
  --border-focus: rgba(0, 240, 255, 0.4);
  --accent-cyan: #00F0FF;
  --accent-cyan-dim: rgba(0, 240, 255, 0.15);
  --accent-emerald: #00FF9D;
  --accent-purple: #8B5CF6;
  --accent-rose: #F43F5E;
  --text-primary: #F8FAFC;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  --font-main: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --radius-xl: 24px;
}

* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family: var(--font-main);
  background: var(--bg-base);
  color: var(--text-primary);
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  -webkit-font-smoothing: antialiased;
}

/* Background Ambient Lighting */
.ambient-glow {
  position: fixed;
  top: -20%;
  left: 20%;
  width: 60vw;
  height: 50vh;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.08) 0%, rgba(0, 240, 255, 0.04) 40%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

/* App Header */
header {
  height: 64px;
  border-bottom: 1px solid var(--border);
  background: rgba(7, 9, 14, 0.8);
  backdrop-filter: blur(20px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  z-index: 10;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: inherit;
}
.brand-logo {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(139, 92, 246, 0.2));
  border: 1px solid rgba(0, 240, 255, 0.3);
  border-radius: var(--radius-sm);
  display: grid;
  place-items: center;
  color: var(--accent-cyan);
}
.brand-title {
  font-weight: 800;
  font-size: 1.15rem;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #FFF 60%, var(--accent-cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.brand-badge {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border);
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--text-secondary);
}

.header-status {
  display: flex;
  align-items: center;
  gap: 12px;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-secondary);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-emerald);
  box-shadow: 0 0 10px var(--accent-emerald);
}
.authority-pill {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(0, 255, 157, 0.1);
  border: 1px solid rgba(0, 255, 157, 0.3);
  color: var(--accent-emerald);
}
.btn-lang {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 0.78rem;
  font-weight: 600;
  transition: all 0.2s;
}
.btn-lang:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
}

/* Layout */
.app-container {
  flex: 1;
  display: flex;
  height: calc(100vh - 64px);
  z-index: 1;
  position: relative;
}

/* Sidebar */
aside.nav-sidebar {
  width: 250px;
  background: rgba(11, 15, 24, 0.7);
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  gap: 8px;
}
.nav-heading {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 10px 12px 4px;
}
.nav-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid transparent;
  font-size: 0.88rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
  text-align: left;
}
.nav-btn:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
}
.nav-btn.active {
  color: var(--accent-cyan);
  background: rgba(0, 240, 255, 0.08);
  border-color: rgba(0, 240, 255, 0.2);
  font-weight: 600;
}
.nav-icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sidebar-spacer { flex: 1; }

.privacy-badge {
  background: rgba(0, 255, 157, 0.05);
  border: 1px solid rgba(0, 255, 157, 0.2);
  border-radius: var(--radius-md);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.privacy-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--accent-emerald);
}
.privacy-text {
  font-size: 0.68rem;
  color: var(--text-muted);
  line-height: 1.4;
}

/* Main Content Area */
main.main-viewport {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: radial-gradient(circle at top right, rgba(15, 23, 42, 0.4), transparent 60%);
}

/* View Sections */
.view-section {
  flex: 1;
  display: none;
  height: 100%;
}
.view-section.active {
  display: flex;
  flex-direction: column;
}

/* Chat View */
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.chat-messages::-webkit-scrollbar { width: 6px; }
.chat-messages::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 999px;
}

/* Message Styles */
.message-row {
  display: flex;
  gap: 12px;
  max-width: 82%;
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
.message-row.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.message-row.bot {
  align-self: flex-start;
}
.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 700;
}
.message-row.user .message-avatar {
  background: linear-gradient(135deg, #6366F1, #8B5CF6);
  color: #FFF;
}
.message-row.bot .message-avatar {
  background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(0, 255, 157, 0.2));
  border: 1px solid rgba(0, 240, 255, 0.3);
  color: var(--accent-cyan);
}
.message-bubble {
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  line-height: 1.6;
  font-size: 0.92rem;
  position: relative;
  word-break: break-word;
}
.message-row.user .message-bubble {
  background: linear-gradient(135deg, #4F46E5, #6366F1);
  color: #FFF;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 16px rgba(79, 70, 229, 0.25);
}
.message-row.bot .message-bubble {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  backdrop-filter: blur(16px);
}
.message-bubble pre {
  background: #0B0E17;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-sm);
  padding: 12px;
  margin: 10px 0;
  font-family: var(--font-mono);
  font-size: 0.82rem;
  overflow-x: auto;
}
.message-bubble code {
  font-family: var(--font-mono);
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
}
.message-bubble pre code {
  background: transparent;
  padding: 0;
}

/* Step Progress Card */
.progress-card {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(0, 240, 255, 0.25);
  border-radius: var(--radius-md);
  padding: 14px 18px;
  margin: 6px 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.progress-title {
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--accent-cyan);
  display: flex;
  align-items: center;
  gap: 8px;
}
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0, 240, 255, 0.2);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.progress-step-item {
  font-size: 0.78rem;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-badge {
  font-size: 0.7rem;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--accent-cyan);
}

/* System Banner Notice */
.system-notice {
  align-self: center;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid var(--border);
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 0.76rem;
  color: var(--text-muted);
}
.mic-alert-banner {
  background: rgba(244, 63, 94, 0.12);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: #FDA4AF;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  font-size: 0.82rem;
  margin: 0 32px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* Chat Input Bar */
.chat-input-wrapper {
  padding: 12px 32px 20px;
  background: linear-gradient(to top, var(--bg-base) 80%, transparent);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.action-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
}
.action-chips::-webkit-scrollbar { display: none; }
.chip-btn {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.18s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.chip-btn:hover {
  background: rgba(0, 240, 255, 0.08);
  border-color: rgba(0, 240, 255, 0.3);
  color: var(--accent-cyan);
}

.input-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  backdrop-filter: blur(20px);
  padding: 6px 10px 6px 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all 0.2s;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
.input-box:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 2px rgba(0, 240, 255, 0.15), 0 8px 32px rgba(0, 0, 0, 0.4);
}
.input-box textarea {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-family: var(--font-main);
  font-size: 0.94rem;
  resize: none;
  max-height: 120px;
  line-height: 1.5;
  padding: 8px 0;
}
.input-box textarea::placeholder { color: var(--text-muted); }

.btn-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-secondary);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.btn-icon:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
}
.btn-mic.recording {
  background: rgba(244, 63, 94, 0.2);
  color: var(--accent-rose);
  animation: pulse 1.2s infinite;
}
@keyframes pulse {
  0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(244, 63, 94, 0.4); }
  70% { transform: scale(1.08); box-shadow: 0 0 0 10px rgba(244, 63, 94, 0); }
  100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(244, 63, 94, 0); }
}
.btn-send {
  background: linear-gradient(135deg, #00F0FF, #00FF9D);
  color: #07090E;
  font-weight: 700;
}
.btn-send:hover {
  filter: brightness(1.15);
  transform: scale(1.04);
}

/* Settings & Hardware Views */
.scroll-view {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.section-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.section-title {
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}
.section-subtitle {
  font-size: 0.85rem;
  color: var(--text-muted);
}
.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
}
.setting-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  backdrop-filter: blur(20px);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-head-title {
  font-weight: 700;
  font-size: 0.96rem;
}
.card-head-desc {
  font-size: 0.8rem;
  color: var(--text-muted);
}
.select-input {
  width: 100%;
  background: #0B0E17;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: var(--font-main);
  font-size: 0.88rem;
  padding: 10px 14px;
  outline: none;
  cursor: pointer;
}
.select-input:focus { border-color: var(--accent-cyan); }

.radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.radio-option {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
}
.radio-option:hover {
  background: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.15);
}
.radio-option.selected {
  background: rgba(0, 240, 255, 0.06);
  border-color: var(--accent-cyan);
}
.radio-option input { margin-top: 4px; }
.radio-label-title { font-size: 0.88rem; font-weight: 600; }
.radio-label-desc { font-size: 0.76rem; color: var(--text-muted); margin-top: 2px; }

/* Metrics Gauge */
.metric-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.metric-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.82rem;
  font-weight: 600;
}
.metric-track {
  height: 8px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 999px;
  overflow: hidden;
}
.metric-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1);
}
.fill-cyan { background: linear-gradient(90deg, #00F0FF, #00FF9D); }
.fill-purple { background: linear-gradient(90deg, #8B5CF6, #EC4899); }

/* Tool Search & Directory */
.tool-search-box {
  width: 100%;
  background: #0B0E17;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: var(--font-main);
  padding: 10px 16px;
  outline: none;
  font-size: 0.88rem;
}
.tool-search-box:focus { border-color: var(--accent-cyan); }
.tool-list-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  max-height: 480px;
  overflow-y: auto;
  padding-right: 6px;
}
.tool-item-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tool-item-name {
  font-family: var(--font-mono);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent-cyan);
}
.tool-item-desc {
  font-size: 0.74rem;
  color: var(--text-muted);
  line-height: 1.4;
}
</style>
</head>
<body>

<div class="ambient-glow"></div>

<header>
  <a href="#" class="brand">
    <div class="brand-logo">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
        <polyline points="2 17 12 22 22 17"></polyline>
        <polyline points="2 12 12 17 22 12"></polyline>
      </svg>
    </div>
    <div class="brand-title">OMNICORE</div>
    <div class="brand-badge">v0.40.0</div>
  </a>

  <div class="header-status">
    <div class="status-pill">
      <span class="status-dot"></span>
      <span id="headerProviderModel">Bağlanıyor...</span>
    </div>
    <div class="authority-pill" id="headerAuthority">🔓 TAM YETKİ</div>
    <button class="btn-lang" id="btnHeaderVoice" onclick="toggleVoiceInput()" title="Sesli Asistan & Mikrofon">🎙️ Ses</button>
    <button class="btn-lang" id="btnLangToggle" onclick="toggleLanguage()">🇹🇷 TR</button>
  </div>
</header>

<div class="app-container">
  <!-- Navigation Sidebar -->
  <aside class="nav-sidebar">
    <div class="nav-heading" data-i18n="nav_heading">Gezinti</div>
    
    <button class="nav-btn active" onclick="switchView('chat')">
      <span class="nav-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
      </span>
      <span data-i18n="nav_chat">Yapay Zeka Sohbet</span>
    </button>

    <button class="nav-btn" onclick="toggleVoiceInput()" id="btnNavVoice" title="Sesli Asistan (Voice Duplex)">
      <span class="nav-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
          <line x1="12" y1="19" x2="12" y2="23"></line>
          <line x1="8" y1="23" x2="16" y2="23"></line>
        </svg>
      </span>
      <span data-i18n="nav_voice">Sesli Asistan</span>
    </button>

    <button class="nav-btn" onclick="switchView('settings')">
      <span class="nav-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
      </span>
      <span data-i18n="nav_settings">Sistem & Yetki Ayarları</span>
    </button>

    <button class="nav-btn" onclick="switchView('resources')">
      <span class="nav-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
          <line x1="6" y1="6" x2="6.01" y2="6"></line>
          <line x1="6" y1="18" x2="6.01" y2="18"></line>
        </svg>
      </span>
      <span data-i18n="nav_resources">Sistem Bilgisi & Araçlar</span>
    </button>

    <div class="sidebar-spacer"></div>

    <div class="privacy-badge">
      <div class="privacy-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
        </svg>
        <span data-i18n="privacy_title">%100 Yerel Gizlilik</span>
      </div>
      <div class="privacy-text" data-i18n="privacy_desc">
        OmniCore tamamen cihazınızda çalışır. Donanım bilgisi ve kullanım verileriniz dış sunuculara kesinlikle aktarılmaz.
      </div>
    </div>
  </aside>

  <!-- Main Viewport -->
  <main class="main-viewport">
    <!-- View 1: Chat -->
    <section class="view-section active" id="view-chat">
      <div class="chat-container">
        <div id="micAlert" class="mic-alert-banner" style="display:none;">
          <span data-i18n="mic_blocked_msg">🎙️ Mikrofon izni engellendi: Tarayıcı adres çubuğundaki kilit simgesine (🔒) tıklayıp Mikrofona izin verin.</span>
          <button class="btn-icon" style="width:24px;height:24px;" onclick="document.getElementById('micAlert').style.display='none'">✕</button>
        </div>

        <div class="chat-messages" id="messagesList">
          <div class="system-notice" data-i18n="welcome_msg">
            OmniCore Yapay Zeka İşletim Sistemine Hoş Geldiniz. Doğal dilde talimat verin.
          </div>
        </div>

        <!-- Chat Input Area -->
        <div class="chat-input-wrapper">
          <div class="action-chips">
            <button class="chip-btn" onclick="sendPrompt('Ruhi Çenet YouTube son videosunu aç')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
              Ruhi Çenet YouTube Aç
            </button>
            <button class="chip-btn" onclick="sendPrompt('Masaüstünün ekran görüntüsünü alıp kaydet')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
              Ekran Görüntüsü Al
            </button>
            <button class="chip-btn" onclick="sendPrompt('Spotify uygulamasını aç ve müziği oynat')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
              Spotify Müziği Aç
            </button>
            <button class="chip-btn" onclick="sendPrompt('/status')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg>
              /status (Sistem Durumu)
            </button>
            <button class="chip-btn" onclick="sendPrompt('/models')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>
              /models (Model Havuzu)
            </button>
          </div>

          <div class="input-box">
            <button class="btn-icon btn-mic" id="btnMic" onclick="toggleVoiceInput()" title="Sesli Konuş">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
              </svg>
            </button>
            <textarea id="chatInput" rows="1" placeholder="OmniCore'a bir talimat verin..." onkeydown="handleInputKey(event)"></textarea>
            <button class="btn-icon btn-send" onclick="sendCurrentMessage()" title="Gönder">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- View 2: Settings -->
    <section class="view-section" id="view-settings">
      <div class="scroll-view">
        <div class="section-header">
          <div class="section-title" data-i18n="settings_title">Model & Güvenlik Yönetimi</div>
          <div class="section-subtitle" data-i18n="settings_subtitle">Degisiklikler aninda bellege ve .env dosyasina kaydedilir.</div>
        </div>

        <div class="grid-cards">
          <!-- Model Selection -->
          <div class="setting-card">
            <div class="card-head">
              <div class="card-head-title" data-i18n="active_model_title">Aktif Model & Sağlayıcı</div>
              <span class="badge" id="lblCurrentModel">...</span>
            </div>
            <div class="card-head-desc" data-i18n="active_model_desc">Kullanmak istediğiniz birincil yapay zeka modelini seçin.</div>
            <select class="select-input" id="selModelList" onchange="onModelSelected(this.value)">
              <option>Yükleniyor...</option>
            </select>
          </div>

          <!-- Authority Mode -->
          <div class="setting-card">
            <div class="card-head">
              <div class="card-head-title" data-i18n="perm_mode_title">İzin & Yetki Modu</div>
            </div>
            <div class="card-head-desc" data-i18n="perm_mode_desc">Otonom araçların çalışma onay politikasını yapılandırın.</div>
            <div class="radio-group">
              <label class="radio-option" id="opt-full" onclick="setAuthorityMode('full')">
                <input type="radio" name="permMode" value="full">
                <div>
                  <div class="radio-label-title">🔓 Tam Yetki (Full Authority)</div>
                  <div class="radio-label-desc">Ekran görüntüsü, tarayıcı, dosya ve uygulama işlemlerinde onay sormaz. Kesintisiz otonom yürütür.</div>
                </div>
              </label>
              <label class="radio-option" id="opt-safe" onclick="setAuthorityMode('safe')">
                <input type="radio" name="permMode" value="safe">
                <div>
                  <div class="radio-label-title">🔐 Güvenli Mod (Safe Mode)</div>
                  <div class="radio-label-desc">Rutin işlemleri otomatik onaylar, yalnızca kritik sistem/disk eylemleri için sorar.</div>
                </div>
              </label>
              <label class="radio-option" id="opt-ask" onclick="setAuthorityMode('ask')">
                <input type="radio" name="permMode" value="ask">
                <div>
                  <div class="radio-label-title">🔒 Sorarak Onay (Strict Ask)</div>
                  <div class="radio-label-desc">Her araç çalıştırmadan önce kullanıcı onayı bekler.</div>
                </div>
              </label>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- View 3: Hardware & Tools -->
    <section class="view-section" id="view-resources">
      <div class="scroll-view">
        <div class="section-header">
          <div class="section-title" data-i18n="resources_title">Yerel Donanım & Araç Havuzu</div>
          <div class="section-subtitle" data-i18n="resources_subtitle">Cihazınızın sistem kaynakları ve kayıtlı 192+ otonom araç kataloğu.</div>
        </div>

        <div class="grid-cards">
          <!-- Hardware Metrics -->
          <div class="setting-card">
            <div class="card-head">
              <div class="card-head-title" data-i18n="hw_monitor_title">Donanım Kaynakları</div>
              <span class="badge" style="color:var(--accent-emerald)">100% Yerel</span>
            </div>
            <div class="metric-row">
              <div class="metric-meta">
                <span>CPU Kullanımı</span>
                <span id="txtCpuUsage">0%</span>
              </div>
              <div class="metric-track">
                <div class="metric-fill fill-cyan" id="barCpu" style="width:0%"></div>
              </div>
            </div>
            <div class="metric-row">
              <div class="metric-meta">
                <span>RAM Bellek</span>
                <span id="txtRamUsage">0 GB</span>
              </div>
              <div class="metric-track">
                <div class="metric-fill fill-purple" id="barRam" style="width:0%"></div>
              </div>
            </div>
          </div>

          <!-- Privacy Commitment -->
          <div class="setting-card" style="border-color: rgba(0, 255, 157, 0.3);">
            <div class="card-head">
              <div class="card-head-title" style="color:var(--accent-emerald);">🛡️ Gizlilik ve Veri Güvenliği</div>
            </div>
            <div style="font-size:0.84rem; color:var(--text-secondary); line-height:1.6;">
              <p>• <strong>Sıfır Dış Veri Gönderimi:</strong> OmniCore sistem durumu ve donanım bilgisi harici hiçbir şirkete (Google, Meta, bulut servisleri) gönderilmez.</p>
              <p style="margin-top:6px;">• <strong>Lokal psutil Ölçümü:</strong> Tüm CPU ve RAM değerleri doğrudan işletim sistemi çekirdeğinden okunur.</p>
              <p style="margin-top:6px;">• <strong>Vektör Bellek Güvenliği:</strong> ChromaDB üçüncü taraf veri toplama kod düzeyinde kapatılmıştır.</p>
            </div>
          </div>
        </div>

        <!-- Tool Catalog -->
        <div class="setting-card">
          <div class="card-head">
            <div class="card-head-title" data-i18n="tools_title">Kayıtlı Otonom Araçlar (192)</div>
            <input type="text" class="tool-search-box" id="toolFilter" placeholder="Araç ara (örn: youtube, screen, terminal)..." oninput="filterTools(this.value)" style="max-width:320px;">
          </div>
          <div class="tool-list-container" id="toolListContainer">
            <div style="color:var(--text-muted); font-size:0.85rem;">Araç listesi yükleniyor...</div>
          </div>
        </div>
      </div>
    </section>
  </main>
</div>

<script>
// --- State & Localization ---
let currentLang = 'tr';
let currentView = 'chat';

const I18N = {
  tr: {
    nav_heading: "Gezinti",
    nav_chat: "Yapay Zeka Sohbet",
    nav_voice: "Sesli Asistan",
    nav_settings: "Sistem & Yetki Ayarları",
    nav_resources: "Sistem Bilgisi & Araçlar",
    privacy_title: "%100 Yerel Gizlilik",
    privacy_desc: "OmniCore tamamen cihazınızda çalışır. Sistem bilgisi ve kullanım verileriniz dış sunuculara kesinlikle aktarılmaz.",
    welcome_msg: "OmniCore Yapay Zeka İşletim Sistemine Hoş Geldiniz. Doğal dilde talimat verin.",
    mic_blocked_msg: "🎙️ Mikrofon izni engellendi: Tarayıcı adres çubuğundaki kilit simgesine (🔒) tıklayıp Mikrofona izin verin.",
    settings_title: "Model & Güvenlik Yönetimi",
    settings_subtitle: "Degisiklikler aninda bellege ve .env dosyasina kaydedilir.",
    active_model_title: "Aktif Model & Sağlayıcı",
    active_model_desc: "Kullanmak istediğiniz birincil yapay zeka modelini seçin.",
    perm_mode_title: "İzin & Yetki Modu",
    perm_mode_desc: "Otonom araçların çalışma onay politikasını yapılandırın.",
    resources_title: "Sistem Bilgisi & Otonom Araç Havuzu",
    resources_subtitle: "Cihazınızın sistem kaynakları, bellek durumu ve kayıtlı 192+ otonom araç kataloğu.",
    hw_monitor_title: "Sistem Bilgisi (CPU & RAM)",
    tools_title: "Kayıtlı Otonom Araçlar",
  },
  en: {
    nav_heading: "Navigation",
    nav_chat: "AI Chat Assistant",
    nav_voice: "Voice Assistant",
    nav_settings: "System & Authority",
    nav_resources: "System Info & Tools",
    privacy_title: "100% Local Privacy",
    privacy_desc: "OmniCore runs entirely on your device. Hardware metrics and usage data are never transmitted externally.",
    welcome_msg: "Welcome to OmniCore Autonomous AI OS. Provide natural instructions.",
    mic_blocked_msg: "🎙️ Microphone permission blocked: Click the lock icon (🔒) in your browser address bar to allow microphone access.",
    settings_title: "Model & Security Management",
    settings_subtitle: "Changes are instantly persisted to memory and .env.",
    active_model_title: "Active Model & Provider",
    active_model_desc: "Select the primary artificial intelligence model.",
    perm_mode_title: "Authority & Permission Policy",
    perm_mode_desc: "Configure autonomous execution authorization policies.",
    resources_title: "System Info & Tool Catalog",
    resources_subtitle: "Device system health, memory status, and registered 192+ autonomous tools.",
    hw_monitor_title: "System Info (CPU & RAM)",
    tools_title: "Registered Autonomous Tools",
  }
};

function toggleLanguage() {
  currentLang = currentLang === 'tr' ? 'en' : 'tr';
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (I18N[currentLang][key]) el.textContent = I18N[currentLang][key];
  });
}

function switchView(viewName) {
  currentView = viewName;
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));

  const btn = document.querySelector(`button[onclick="switchView('${viewName}')"]`);
  if (btn) btn.classList.add('active');

  const sec = document.getElementById(`view-${viewName}`);
  if (sec) sec.classList.add('active');
}

// --- Voice & Speech Features ---
let speechRecognition = null;
let speechVoice = null;
let voiceActive = false;

if ('speechSynthesis' in window) {
  window.speechSynthesis.onvoiceschanged = () => {
    const voices = window.speechSynthesis.getVoices();
    speechVoice = voices.find(v => v.lang.startsWith(currentLang === 'tr' ? 'tr' : 'en')) || voices[0];
  };
}

function speakText(text) {
  if (!window.speechSynthesis) return;
  const clean = text.replace(/[*_#`~[\]]/g, '').replace(/http\S+/g, '');
  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = currentLang === 'tr' ? 'tr-TR' : 'en-US';
  if (speechVoice) utter.voice = speechVoice;
  window.speechSynthesis.speak(utter);
}

function toggleVoiceInput() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    alert("Tarayıcınız ses tanımayı desteklemiyor. Lütfen Chrome veya Edge kullanın.");
    return;
  }
  if (!speechRecognition) {
    speechRecognition = new SpeechRec();
    speechRecognition.lang = currentLang === 'tr' ? 'tr-TR' : 'en-US';
    speechRecognition.interimResults = true;
    speechRecognition.continuous = false;

    speechRecognition.onstart = () => {
      voiceActive = true;
      document.getElementById('btnMic').classList.add('recording');
    };
    speechRecognition.onresult = (event) => {
      let text = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        text += event.results[i][0].transcript;
      }
      document.getElementById('chatInput').value = text;
      if (event.results[0].isFinal) {
        sendCurrentMessage();
      }
    };
    speechRecognition.onerror = (event) => {
      voiceActive = false;
      document.getElementById('btnMic').classList.remove('recording');
      if (event.error === 'not-allowed') {
        document.getElementById('micAlert').style.display = 'flex';
      }
    };
    speechRecognition.onend = () => {
      voiceActive = false;
      document.getElementById('btnMic').classList.remove('recording');
    };
  }

  if (voiceActive) {
    speechRecognition.stop();
  } else {
    try {
      speechRecognition.start();
    } catch(e) {
      speechRecognition.stop();
    }
  }
}

// --- Chat & Streaming Execution ---
function appendMessage(text, role='bot') {
  const list = document.getElementById('messagesList');
  const row = document.createElement('div');
  row.className = 'message-row ' + role;
  
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? 'YOU' : 'AI';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  
  // Format simple markdown
  bubble.innerHTML = formatMarkdown(text);

  row.appendChild(avatar);
  row.appendChild(bubble);
  list.appendChild(row);
  list.scrollTop = list.scrollHeight;
  return bubble;
}

function formatMarkdown(text) {
  let esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // Code blocks
  esc = esc.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  // Inline code
  esc = esc.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  esc = esc.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Line breaks
  esc = esc.replace(/\n/g, '<br>');
  return esc;
}

function appendProgressCard() {
  const list = document.getElementById('messagesList');
  const card = document.createElement('div');
  card.className = 'progress-card';
  card.id = 'activeProgressCard';

  const title = document.createElement('div');
  title.className = 'progress-title';
  title.innerHTML = '<span class="spinner"></span> <span id="progressTitleText">İşlem analiz ediliyor...</span>';
  card.appendChild(title);

  const stepsContainer = document.createElement('div');
  stepsContainer.id = 'progressStepsContainer';
  stepsContainer.style.display = 'flex';
  stepsContainer.style.flexDirection = 'column';
  stepsContainer.style.gap = '4px';
  card.appendChild(stepsContainer);

  list.appendChild(card);
  list.scrollTop = list.scrollHeight;
  return card;
}

function removeProgressCard() {
  const card = document.getElementById('activeProgressCard');
  if (card) card.remove();
}

function handleInputKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendCurrentMessage();
  }
}

function sendPrompt(text) {
  document.getElementById('chatInput').value = text;
  sendCurrentMessage();
}

async function sendCurrentMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';

  appendMessage(text, 'user');
  const progressCard = appendProgressCard();
  const titleText = document.getElementById('progressTitleText');
  const stepsContainer = document.getElementById('progressStepsContainer');

  // Stream via SSE
  try {
    const url = '/api/chat/stream?message=' + encodeURIComponent(text);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop(); // Keep partial

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.replace(/^data: /, '').trim();
        if (!jsonStr) continue;
        try {
          const payload = JSON.parse(jsonStr);
          handleProgressEvent(payload, titleText, stepsContainer);
        } catch(err) {
          console.error("SSE parse error:", err);
        }
      }
    }
  } catch(err) {
    removeProgressCard();
    appendMessage(`⚠️ İstek yürütülürken hata oluştu: ${err.message}`, 'bot');
  }
}

function handleProgressEvent(event, titleEl, stepsEl) {
  if (event.type === 'thinking') {
    titleEl.textContent = event.data.text || "İstek analiz ediliyor...";
  } else if (event.type === 'plan_ready') {
    const steps = event.data.steps || [];
    titleEl.textContent = `📋 ${steps.length} Adımlı Otonom Plan Yürütülüyor:`;
    stepsEl.innerHTML = '';
    steps.forEach((s, idx) => {
      const item = document.createElement('div');
      item.className = 'progress-step-item';
      item.innerHTML = `<span class="step-badge">${idx+1}/${steps.length}</span> ${s.tool_name}`;
      stepsEl.appendChild(item);
    });
  } else if (event.type === 'step_start') {
    titleEl.textContent = `⚡ [${event.data.step}/${event.data.total}] ${event.data.tool} çalıştırılıyor...`;
  } else if (event.type === 'step_end') {
    const ok = event.data.status === 'ok';
    const item = document.createElement('div');
    item.className = 'progress-step-item';
    item.style.color = ok ? 'var(--accent-emerald)' : 'var(--accent-rose)';
    item.textContent = `${ok ? '✅' : '❌'} ${event.data.tool}: ${event.data.result || 'tamamlandı'}`;
    stepsEl.appendChild(item);
  } else if (event.type === 'summarizing') {
    titleEl.textContent = "✨ Sonuçlar toparlanıyor...";
  } else if (event.type === 'done') {
    removeProgressCard();
    appendMessage(event.reply, 'bot');
    speakText(event.reply);
  } else if (event.type === 'error') {
    removeProgressCard();
    appendMessage(`❌ Hata: ${event.error}`, 'bot');
  }
}

// --- Live System Info & Status ---
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const d = await res.json();
    document.getElementById('headerProviderModel').textContent = `${d.provider} | ${d.model}`;
    document.getElementById('lblCurrentModel').textContent = d.model;

    const modeNames = {
      full: "🔓 TAM YETKİ",
      safe: "🔐 GÜVENLİ MOD",
      ask: "🔒 SORARAK ONAY"
    };
    document.getElementById('headerAuthority').textContent = modeNames[d.approval_mode] || d.approval_mode;

    // Sync radio selection
    document.querySelectorAll('.radio-option').forEach(el => el.classList.remove('selected'));
    const opt = document.getElementById('opt-' + d.approval_mode);
    if (opt) {
      opt.classList.add('selected');
      const radio = opt.querySelector('input');
      if (radio) radio.checked = true;
    }
  } catch(e) { console.error('Status fetch failed:', e); }
}

async function fetchSysinfo() {
  try {
    const res = await fetch('/api/sysinfo');
    const d = await res.json();
    document.getElementById('txtCpuUsage').textContent = d.cpu_percent + '%';
    document.getElementById('barCpu').style.width = Math.min(100, d.cpu_percent) + '%';
    document.getElementById('txtRamUsage').textContent = `${d.ram_percent}% (${d.ram_used_gb} / ${d.ram_total_gb} GB)`;
    document.getElementById('barRam').style.width = Math.min(100, d.ram_percent) + '%';
  } catch(e) { console.error('Sysinfo fetch failed:', e); }
}

async function loadModels() {
  try {
    const res = await fetch('/api/models');
    const d = await res.json();
    const sel = document.getElementById('selModelList');
    sel.innerHTML = '';
    for (const [provider, models] of Object.entries(d)) {
      const grp = document.createElement('optgroup');
      grp.label = provider.toUpperCase();
      for (const m of models) {
        const opt = document.createElement('option');
        opt.value = `${provider}:${m.id}`;
        opt.textContent = `${m.name} (${m.context})`;
        grp.appendChild(opt);
      }
      sel.appendChild(grp);
    }
  } catch(e) { console.error('Models load failed:', e); }
}

let allTools = [];

async function loadTools() {
  try {
    const res = await fetch('/api/tools');
    allTools = await res.json();
    renderTools(allTools);
  } catch(e) { console.error('Tools load failed:', e); }
}

function renderTools(tools) {
  const container = document.getElementById('toolListContainer');
  container.innerHTML = '';
  tools.forEach(t => {
    const card = document.createElement('div');
    card.className = 'tool-item-card';
    card.innerHTML = `
      <div class="tool-item-name">${t.name}</div>
      <div class="tool-item-desc">${t.description || 'Açıklama yok'}</div>
    `;
    container.appendChild(card);
  });
}

function filterTools(query) {
  const q = query.toLowerCase();
  const filtered = allTools.filter(t => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q));
  renderTools(filtered);
}

async function onModelSelected(val) {
  const [provider, model] = val.split(':');
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: 'model', value: model })
  });
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: 'provider', value: provider })
  });
  fetchStatus();
}

async function setAuthorityMode(mode) {
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: 'approval_mode', value: mode })
  });
  fetchStatus();
}

// Init
fetchStatus();
fetchSysinfo();
loadModels();
loadTools();
setInterval(fetchStatus, 4000);
setInterval(fetchSysinfo, 2500);
</script>
</body>
</html>
"""


def _write_to_stderr(msg: str) -> None:
    import sys

    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
