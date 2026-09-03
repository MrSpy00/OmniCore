"""Web Dashboard 2.0 — Modern FastAPI + HTML/CSS/JS frontend for OmniCore.

Features:
- Real-time token streaming typewriter effect via WebSocket (/ws/chat)
- Interactive Cytoscape.js GraphRAG Knowledge Graph visualizer
- Live Process Manager with PID, CPU/RAM telemetry, and single-click termination
- Real brand logo (OmniCore-bounce.png) with neon glow animations for bot avatar and header
- Smart plan card formatter in formatMarkdown() to eliminate raw JSON leaks
- Memory statistics (ChromaDB + SQLite GraphMemory) in sidebar

Launch with: uv run omnicore --mode web
Serves on: http://localhost:8080
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

from config.logging import get_logger
from config.settings import get_settings
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

_router: CognitiveRouter | None = None
_start_time: float = time.time()
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def set_router(router: CognitiveRouter) -> None:
    global _router
    _router = router


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="OmniCore Dashboard 2.0", docs_url="/api/docs")
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
        fav_path = _ASSETS_DIR / "OmniCore-bounce.png"
        if fav_path.exists():
            return FileResponse(fav_path, media_type="image/png")
        return Response(content=b"", media_type="image/x-icon")

    @app.get("/assets/{filename}")
    async def get_asset(filename: str):
        asset_file = _ASSETS_DIR / filename
        if asset_file.exists() and asset_file.is_file():
            media_type = "image/png" if filename.endswith(".png") else "application/octet-stream"
            return FileResponse(asset_file, media_type=media_type)
        return Response(status_code=404)

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

    @app.get("/api/memory/stats")
    async def api_memory_stats():
        """Return memory statistics (ChromaDB document count and GraphMemory stats)."""
        doc_count = 0
        nodes_count = 0
        edges_count = 0
        if _router and hasattr(_router, "_long_term"):
            try:
                doc_count = _router._long_term.count()
            except Exception:
                pass
        try:
            from memory.graph_memory import GraphMemory

            gm = GraphMemory()
            try:
                await gm.initialize()
                data = await gm.export_graph_data()
                nodes_count = len(data.get("nodes", []))
                edges_count = len(data.get("edges", []))
            finally:
                await gm.close()
        except Exception:
            pass
        return {
            "total_documents": doc_count,
            "graph_nodes": nodes_count,
            "graph_edges": edges_count,
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
                    reply = await _router.handle_message(msg, "web_session", on_progress=on_progress)
                    # Progressive token streaming for SSE
                    words = reply.split(" ")
                    for i, w in enumerate(words):
                        chunk = w if i == 0 else " " + w
                        await queue.put({"type": "token", "token": chunk})
                        await asyncio.sleep(0.012)
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

    @app.get("/api/graph/data")
    async def api_graph_data():
        """Return full Knowledge Graph (GraphRAG) nodes and edges for Cytoscape.js."""
        try:
            from memory.graph_memory import GraphMemory

            gm = GraphMemory()
            try:
                await gm.initialize()
                data = await gm.export_graph_data()
                return data
            finally:
                await gm.close()
        except Exception as exc:
            logger.error("dashboard.graph_data_error", error=str(exc))
            return {"nodes": [], "edges": [], "count": 0, "error": str(exc)}

    @app.get("/api/system/processes")
    async def api_system_processes(limit: int = 25):
        """Return top system processes sorted by CPU and memory consumption."""
        import psutil

        procs: list[dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                if info.get("name"):
                    procs.append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu": round(info.get("cpu_percent") or 0.0, 1),
                        "ram": round(info.get("memory_percent") or 0.0, 1),
                    })
            except Exception:
                pass
        procs.sort(key=lambda x: (x["cpu"], x["ram"]), reverse=True)
        return procs[:limit]

    @app.post("/api/system/kill-process")
    async def api_system_kill_process(request: Request):
        """Terminate a process by PID."""
        import psutil

        body = await request.json()
        pid = body.get("pid")
        if not pid:
            return JSONResponse({"error": "Missing pid parameter"}, status_code=400)
        try:
            p = psutil.Process(int(pid))
            name = p.name()
            p.terminate()
            return {"success": True, "message": f"Süreç '{name}' (PID: {pid}) sonlandırıldı."}
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        """Bidirectional WebSocket for real-time streaming chat with typewriter effect."""
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                    user_text = payload.get("message", "").strip()
                except Exception:
                    user_text = data.strip()

                if not user_text:
                    continue

                if not _router:
                    await websocket.send_text(json.dumps({"type": "error", "error": "Router not ready"}))
                    continue

                msg = Message(
                    role=MessageRole.USER,
                    content=user_text,
                    channel="websocket",
                    user_id="ws_user",
                )

                async def ws_progress(event_type: str, evt_data: dict[str, Any]):
                    try:
                        await websocket.send_text(
                            json.dumps({"type": event_type, "data": evt_data}, ensure_ascii=False)
                        )
                    except Exception:
                        pass

                try:
                    reply = await _router.handle_message(msg, "ws_session", on_progress=ws_progress)
                    # Progressive streaming typewriter tokens
                    words = reply.split(" ")
                    for i, w in enumerate(words):
                        chunk = w if i == 0 else " " + w
                        await websocket.send_text(json.dumps({"type": "token", "token": chunk}, ensure_ascii=False))
                        await asyncio.sleep(0.015)
                    await websocket.send_text(json.dumps({"type": "done", "reply": reply}, ensure_ascii=False))
                except Exception as exc:
                    logger.error("dashboard.ws_error", error=str(exc))
                    await websocket.send_text(json.dumps({"type": "error", "error": str(exc)}))
        except WebSocketDisconnect:
            pass

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


# Premium Cyber-Obsidian UI 2.0 - Zero AI Slop, Inline SVGs, Cytoscape GraphRAG, Process Manager
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniCore — Sovereign Autonomous AI OS</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<!-- Cytoscape.js for GraphRAG Knowledge Graph Visualization -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.29.2/cytoscape.min.js"></script>
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

/* Ambient Lighting */
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
  background: rgba(7, 9, 14, 0.85);
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
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(139, 92, 246, 0.2));
  border: 1px solid rgba(0, 240, 255, 0.4);
  border-radius: var(--radius-sm);
  display: grid;
  place-items: center;
  overflow: hidden;
}
.brand-logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), filter 0.3s ease;
  filter: drop-shadow(0 0 6px rgba(0, 240, 255, 0.5));
}
.brand-logo-img:hover {
  transform: scale(1.15) rotate(3deg);
  filter: drop-shadow(0 0 12px rgba(0, 240, 255, 0.9));
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
  width: 260px;
  background: rgba(11, 15, 24, 0.75);
  backdrop-filter: blur(20px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  gap: 6px;
}
.nav-heading {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 8px 12px 4px;
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
  width: 100%;
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
  font-size: 1rem;
}

.sidebar-spacer { flex: 1; }

/* Memory Stats Card */
.memory-stats-card {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(139, 92, 246, 0.25);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 6px;
}
.memory-stats-title {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--accent-purple);
  display: flex;
  align-items: center;
  gap: 6px;
}
.memory-stat-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.7rem;
  color: var(--text-secondary);
}
.memory-stat-val {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-primary);
}

.privacy-badge {
  background: rgba(0, 255, 157, 0.05);
  border: 1px solid rgba(0, 255, 157, 0.2);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.privacy-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--accent-emerald);
}
.privacy-text {
  font-size: 0.66rem;
  color: var(--text-muted);
  line-height: 1.35;
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
  overflow: hidden;
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
  max-width: 85%;
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
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 700;
  overflow: hidden;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
}
.message-row.user .message-avatar {
  background: linear-gradient(135deg, #4F46E5, #8B5CF6);
  color: #FFF;
}
.message-row.bot .message-avatar {
  background: #0B0E17;
  border: 1px solid rgba(0, 240, 255, 0.4);
}
.bot-avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
  filter: drop-shadow(0 0 4px rgba(0, 240, 255, 0.6));
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

/* Typewriter cursor */
.typing-cursor {
  display: inline-block;
  color: var(--accent-cyan);
  font-weight: 700;
  animation: cursorBlink 0.7s infinite;
  margin-left: 2px;
}
@keyframes cursorBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* Plan Card Visualizer */
.rendered-plan-card {
  background: rgba(11, 15, 24, 0.85);
  border: 1px solid rgba(0, 240, 255, 0.3);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  margin: 8px 0;
  box-shadow: 0 4px 20px rgba(0, 240, 255, 0.1);
}
.plan-card-header {
  font-size: 0.86rem;
  color: var(--accent-cyan);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.plan-steps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.plan-step-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  padding: 8px 12px;
  border-radius: var(--radius-sm);
}
.step-num {
  background: rgba(0, 240, 255, 0.15);
  color: var(--accent-cyan);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
}
.step-info {
  flex: 1;
}
.step-desc {
  font-size: 0.84rem;
  color: var(--text-primary);
  font-weight: 500;
}
.step-tool {
  margin-top: 3px;
}
.tool-tag {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  background: rgba(139, 92, 246, 0.15);
  color: #C4B5FD;
  padding: 1px 6px;
  border-radius: 4px;
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
  padding: 6px 0;
}
.input-box textarea::placeholder { color: var(--text-muted); }
.btn-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: all 0.18s;
}
.btn-icon:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.08);
}
.btn-send {
  background: var(--accent-cyan);
  color: #07090E;
}
.btn-send:hover {
  background: #25F4FF;
  transform: scale(1.05);
  box-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
}
.btn-mic.recording {
  background: var(--accent-rose);
  color: #FFF;
  animation: pulse 1s infinite alternate;
}
@keyframes pulse {
  from { box-shadow: 0 0 0 0 rgba(244, 63, 94, 0.6); }
  to { box-shadow: 0 0 0 10px rgba(244, 63, 94, 0); }
}

/* Common View Header */
.view-header {
  padding: 20px 32px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(11, 15, 24, 0.4);
}
.view-title-group h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.view-title-group p {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 2px;
}
.view-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.btn-action {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
}
.btn-action:hover {
  background: rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.3);
  color: var(--accent-cyan);
}

/* GraphRAG View */
.graph-container {
  flex: 1;
  position: relative;
  background: #06080D;
  overflow: hidden;
}
#cyGraph {
  width: 100%;
  height: 100%;
}
.graph-drawer {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 280px;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  backdrop-filter: blur(16px);
  padding: 14px;
  display: none;
  flex-direction: column;
  gap: 8px;
  z-index: 5;
}
.graph-drawer-title {
  font-size: 0.84rem;
  font-weight: 700;
  color: var(--accent-cyan);
}
.graph-drawer-body {
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* Process Manager View */
.process-content {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.proc-search-input {
  background: #0B0E17;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: var(--font-main);
  padding: 8px 14px;
  font-size: 0.82rem;
  outline: none;
  width: 260px;
}
.proc-search-input:focus { border-color: var(--accent-cyan); }
.process-table-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.process-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.process-table th {
  background: rgba(255, 255, 255, 0.02);
  padding: 12px 18px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}
.process-table td {
  padding: 12px 18px;
  font-size: 0.82rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.process-table tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}
.pid-tag {
  font-family: var(--font-mono);
  color: var(--text-muted);
}
.proc-name {
  font-weight: 600;
  color: var(--text-primary);
}
.btn-kill {
  background: rgba(244, 63, 94, 0.1);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: var(--accent-rose);
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
}
.btn-kill:hover {
  background: var(--accent-rose);
  color: #FFF;
}

/* Settings & Resources Views */
.settings-content, .resources-content {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 900px;
}
.card-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.card-section h3 {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.select-input {
  width: 100%;
  background: #0B0E17;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
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
      <img src="/assets/OmniCore-bounce.png" alt="OmniCore Logo" class="brand-logo-img" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';" />
      <svg style="display:none;" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
        <polyline points="2 17 12 22 22 17"></polyline>
        <polyline points="2 12 12 17 22 12"></polyline>
      </svg>
    </div>
    <div class="brand-title">OMNICORE</div>
    <div class="brand-badge">v0.1.0</div>
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

    <button class="nav-btn active" onclick="switchView('chat')" id="nav-chat">
      <span class="nav-icon">💬</span>
      <span data-i18n="nav_chat">Yapay Zeka Sohbet</span>
    </button>

    <button class="nav-btn" onclick="switchView('graph')" id="nav-graph">
      <span class="nav-icon">🧠</span>
      <span>Bilgi Grafiği (GraphRAG)</span>
    </button>

    <button class="nav-btn" onclick="switchView('processes')" id="nav-processes">
      <span class="nav-icon">⚡</span>
      <span>Süreç Yöneticisi</span>
    </button>

    <button class="nav-btn" onclick="switchView('settings')" id="nav-settings">
      <span class="nav-icon">⚙️</span>
      <span data-i18n="nav_settings">Sistem & Yetki</span>
    </button>

    <button class="nav-btn" onclick="switchView('resources')" id="nav-resources">
      <span class="nav-icon">🛠️</span>
      <span data-i18n="nav_resources">Donanım & Araçlar</span>
    </button>

    <div class="sidebar-spacer"></div>

    <!-- Memory Stats Card -->
    <div class="memory-stats-card" id="memStatsCard">
      <div class="memory-stats-title">
        <span>💾</span> Bellek & Bilgi Tabanı
      </div>
      <div class="memory-stat-row">
        <span>Kalıcı Kayıt:</span>
        <span class="memory-stat-val" id="statMemDocs">--</span>
      </div>
      <div class="memory-stat-row">
        <span>Graf Düğümleri:</span>
        <span class="memory-stat-val" id="statGraphNodes">--</span>
      </div>
      <div class="memory-stat-row">
        <span>Graf İlişkileri:</span>
        <span class="memory-stat-val" id="statGraphEdges">--</span>
      </div>
    </div>

    <div class="privacy-badge">
      <div class="privacy-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
        </svg>
        <span data-i18n="privacy_title">%100 Yerel Gizlilik</span>
      </div>
      <div class="privacy-text" data-i18n="privacy_desc">
        OmniCore tamamen cihazınızda çalışır. Verileriniz dış sunuculara kesinlikle aktarılmaz.
      </div>
    </div>
  </aside>

  <!-- Main Viewport -->
  <main class="main-viewport">
    <!-- View 1: Chat -->
    <section class="view-section active" id="view-chat">
      <div class="chat-container">
        <div class="chat-messages" id="messagesList">
          <div class="message-row bot">
            <div class="message-avatar">
              <img src="/assets/OmniCore-bounce.png" alt="OmniCore" class="bot-avatar-img" onerror="this.outerHTML='🤖';" />
            </div>
            <div class="message-bubble">
              👋 <strong>OmniCore Sovereign AI OS</strong> hazır! Nasıl yardımcı olabilirim?
            </div>
          </div>
        </div>

        <div class="chat-input-wrapper">
          <div class="action-chips">
            <button class="chip-btn" onclick="sendPrompt('Spotify\'da sevdiğim şarkıyı çal')">🎵 Spotify Çal</button>
            <button class="chip-btn" onclick="sendPrompt('Şu an ekrana bak ve açık olan pencereyi özetle')">👁️ Ekrana Bak</button>
            <button class="chip-btn" onclick="sendPrompt('Donanım durumunu ve GPU VRAM basıncını göster')">⚡ Sistem & VRAM</button>
            <button class="chip-btn" onclick="sendPrompt('Hakkımda bildiğin kalıcı tercihleri ve notları listele')">🧠 Hafıza Özeti</button>
          </div>

          <div class="input-box">
            <button class="btn-icon btn-mic" id="btnMic" onclick="toggleVoiceInput()" title="Sesle Konuş">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" y1="19" x2="12" y2="23"></line>
                <line x1="8" y1="23" x2="16" y2="23"></line>
              </svg>
            </button>
            <textarea id="chatInput" rows="1" placeholder="Bir mesaj veya otonom komut yazın... (Enter ile gönder)" onkeydown="handleInputKey(event)"></textarea>
            <button class="btn-icon btn-send" onclick="sendCurrentMessage()" title="Gönder">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- View 2: GraphRAG Knowledge Graph -->
    <section class="view-section" id="view-graph">
      <div class="view-header">
        <div class="view-title-group">
          <h2>🧠 GraphRAG Bilgi Grafiği</h2>
          <p>Kalıcı anlamsal ilişkiler, varlık ağları ve çok adımlı çıkarım haritası</p>
        </div>
        <div class="view-actions">
          <button class="btn-action" onclick="loadGraphData()">🔄 Yenile</button>
          <button class="btn-action" onclick="fitGraph()">🎯 Ekrana Sığdır</button>
        </div>
      </div>
      <div class="graph-container">
        <div id="cyGraph"></div>
        <div class="graph-drawer" id="graphDrawer">
          <div class="graph-drawer-title" id="drawerTitle">Varlık Detayı</div>
          <div class="graph-drawer-body" id="drawerBody">Seçilen düğümün bilgileri burada görüntülenir.</div>
        </div>
      </div>
    </section>

    <!-- View 3: Process Manager -->
    <section class="view-section" id="view-processes">
      <div class="view-header">
        <div class="view-title-group">
          <h2>⚡ Süreç Yöneticisi</h2>
          <p>Aktif sistem süreçleri, kaynak tüketimi ve anında sonlandırma kontrolü</p>
        </div>
        <div class="view-actions">
          <input type="text" id="procSearchInput" class="proc-search-input" placeholder="Süreç filtrele..." oninput="filterProcesses()" />
          <button class="btn-action" onclick="loadProcesses()">🔄 Yenile</button>
        </div>
      </div>
      <div class="process-content">
        <div class="process-table-card">
          <table class="process-table">
            <thead>
              <tr>
                <th>PID</th>
                <th>Süreç Adı</th>
                <th>CPU (%)</th>
                <th>Bellek (%)</th>
                <th>Aksiyon</th>
              </tr>
            </thead>
            <tbody id="procTableBody">
              <tr>
                <td colspan="5" style="text-align:center; padding: 24px; color: var(--text-muted);">Yükleniyor...</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- View 4: Settings -->
    <section class="view-section" id="view-settings">
      <div class="view-header">
        <div class="view-title-group">
          <h2>⚙️ Sistem & Yetki Yapılandırması</h2>
          <p>Bilişsel model ve otonom eylem güvenlik seviyesi ayarları</p>
        </div>
      </div>
      <div class="settings-content">
        <div class="card-section">
          <h3>🤖 Aktif Yapay Zeka Modeli</h3>
          <p style="font-size: 0.8rem; color: var(--text-muted);">Kullanılacak LLM sağlayıcısını ve modelini dinamik olarak değiştirin:</p>
          <select class="select-input" id="selModelList" onchange="onModelSelected(this.value)">
            <option value="">Modeller yükleniyor...</option>
          </select>
        </div>

        <div class="card-section">
          <h3>🛡️ Güvenlik ve Eylem Onay Modu</h3>
          <div class="radio-group">
            <div class="radio-option" id="opt-full" onclick="setAuthorityMode('full')">
              <input type="radio" name="perm_mode" value="full" />
              <div>
                <div class="radio-label-title">🔓 Tam Yetki (Full Auto)</div>
                <div class="radio-label-desc">Tüm araçlar, komutlar ve sistem işlemleri kullanıcı onayı beklemeden yürütülür.</div>
              </div>
            </div>
            <div class="radio-option" id="opt-safe" onclick="setAuthorityMode('safe')">
              <input type="radio" name="perm_mode" value="safe" />
              <div>
                <div class="radio-label-title">🔐 Güvenli Mod (Safe Auto)</div>
                <div class="radio-label-desc">Okuma ve arama işlemleri otomatik, dosya silme veya kritik sistem işlemleri onay sorar.</div>
              </div>
            </div>
            <div class="radio-option" id="opt-ask" onclick="setAuthorityMode('ask')">
              <input type="radio" name="perm_mode" value="ask" />
              <div>
                <div class="radio-label-title">🔒 Sorarak Onay (Strict Ask)</div>
                <div class="radio-label-desc">Tüm eylemler yürütülmeden önce kullanıcıdan açık onay talep eder.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- View 5: Resources & Tools -->
    <section class="view-section" id="view-resources">
      <div class="view-header">
        <div class="view-title-group">
          <h2>🛠️ Sistem Kaynakları & Araç Kataloğu</h2>
          <p>Donanım telemetrisi ve OmniCore'un kullanabildiği kayıtlı 60+ otonom araç</p>
        </div>
      </div>
      <div class="resources-content">
        <div class="card-section">
          <h3>💻 Canlı Donanım Telemetrisi</h3>
          <div class="metric-row">
            <div class="metric-meta">
              <span>İşlemci (CPU)</span>
              <span id="txtCpuUsage">--%</span>
            </div>
            <div class="metric-track">
              <div class="metric-fill fill-cyan" id="barCpu" style="width: 0%"></div>
            </div>
          </div>
          <div class="metric-row" style="margin-top: 10px;">
            <div class="metric-meta">
              <span>Bellek (RAM)</span>
              <span id="txtRamUsage">--%</span>
            </div>
            <div class="metric-track">
              <div class="metric-fill fill-purple" id="barRam" style="width: 0%"></div>
            </div>
          </div>
        </div>

        <div class="card-section">
          <h3>🔧 Araç Havuzu</h3>
          <input type="text" class="tool-search-box" placeholder="Araç adı veya açıklamasıyla filtreleyin..." oninput="filterTools(this.value)" />
          <div class="tool-list-container" id="toolListContainer"></div>
        </div>
      </div>
    </section>
  </main>
</div>

<script>
// --- Navigation & View Switching ---
function switchView(viewId) {
  document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));

  const targetView = document.getElementById('view-' + viewId);
  const targetNav = document.getElementById('nav-' + viewId);
  if (targetView) targetView.classList.add('active');
  if (targetNav) targetNav.classList.add('active');

  if (viewId === 'graph') {
    setTimeout(loadGraphData, 100);
  } else if (viewId === 'processes') {
    loadProcesses();
  }
}

// --- WebSocket Chat Engine with Typewriter Streaming ---
let chatSocket = null;
let activeBotBubble = null;
let activeCursor = null;

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
  chatSocket = new WebSocket(wsUrl);

  chatSocket.onopen = () => {
    console.log("WebSocket connected to /ws/chat");
  };

  chatSocket.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data);
      handleWsMessage(payload);
    } catch(err) {
      console.error("WS parse error:", err);
    }
  };

  chatSocket.onclose = () => {
    console.warn("WebSocket closed, attempting reconnect in 3s...");
    setTimeout(initWebSocket, 3000);
  };
}

function handleWsMessage(event) {
  const titleText = document.getElementById('progressTitleText');
  const stepsContainer = document.getElementById('progressStepsContainer');

  if (event.type === 'thinking') {
    if (titleText) titleText.textContent = event.data.text || "İstek analiz ediliyor...";
  } else if (event.type === 'plan_created') {
    if (titleText) titleText.textContent = `📋 ${event.data.total} Adımlı Plan Yürütülüyor:`;
    if (stepsContainer) {
      stepsContainer.innerHTML = '';
      (event.data.steps || []).forEach(s => {
        const item = document.createElement('div');
        item.className = 'progress-step-item';
        item.innerHTML = `<span class="step-badge">${s.step}/${event.data.total}</span> ${s.tool}: ${s.description}`;
        stepsContainer.appendChild(item);
      });
    }
  } else if (event.type === 'step_start') {
    if (titleText) titleText.textContent = `⚡ [${event.data.step}/${event.data.total}] ${event.data.tool} yürütülüyor...`;
  } else if (event.type === 'step_end') {
    if (stepsContainer) {
      const item = document.createElement('div');
      item.className = 'progress-step-item';
      const ok = event.data.status === 'ok';
      item.style.color = ok ? 'var(--accent-emerald)' : 'var(--accent-rose)';
      item.textContent = `${ok ? '✅' : '❌'} ${event.data.tool}: ${event.data.result || 'tamamlandı'}`;
      stepsContainer.appendChild(item);
    }
  } else if (event.type === 'summarizing') {
    if (titleText) titleText.textContent = "✨ Sonuçlar toparlanıyor...";
  } else if (event.type === 'token') {
    // Typewriter token append
    if (!activeBotBubble) {
      removeProgressCard();
      activeBotBubble = appendMessage('', 'bot');
      activeCursor = document.createElement('span');
      activeCursor.className = 'typing-cursor';
      activeCursor.textContent = '▌';
      activeBotBubble.appendChild(activeCursor);
    }
    const tokenSpan = document.createElement('span');
    tokenSpan.textContent = event.token;
    if (activeCursor && activeCursor.parentNode === activeBotBubble) {
      activeBotBubble.insertBefore(tokenSpan, activeCursor);
    } else {
      activeBotBubble.appendChild(tokenSpan);
    }
    const list = document.getElementById('messagesList');
    list.scrollTop = list.scrollHeight;
  } else if (event.type === 'done') {
    removeProgressCard();
    if (activeCursor) {
      activeCursor.remove();
      activeCursor = null;
    }
    if (activeBotBubble) {
      activeBotBubble.innerHTML = formatMarkdown(event.reply);
      activeBotBubble = null;
    } else {
      appendMessage(event.reply, 'bot');
    }
    speakText(event.reply);
  } else if (event.type === 'error') {
    removeProgressCard();
    if (activeCursor) { activeCursor.remove(); activeCursor = null; }
    appendMessage(`❌ Hata: ${event.error}`, 'bot');
    activeBotBubble = null;
  }
}

// --- Message Rendering & Formatting ---
function appendMessage(text, role='bot') {
  const list = document.getElementById('messagesList');
  const row = document.createElement('div');
  row.className = 'message-row ' + role;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar ' + role;
  if (role === 'user') {
    avatar.textContent = 'YOU';
  } else {
    avatar.innerHTML = '<img src="/assets/OmniCore-bounce.png" class="bot-avatar-img" alt="OmniCore" onerror="this.outerHTML=\'🤖\';">';
  }

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  if (text) {
    bubble.innerHTML = formatMarkdown(text);
  }

  row.appendChild(avatar);
  row.appendChild(bubble);
  list.appendChild(row);
  list.scrollTop = list.scrollHeight;
  return bubble;
}

function formatMarkdown(text) {
  if (!text) return '';

  const trimmed = text.trim();
  let jsonPlan = null;
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('```json') && trimmed.endsWith('```'))) {
    try {
      const cleanJson = trimmed.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
      const parsed = JSON.parse(cleanJson);
      if (parsed && (parsed.needs_plan !== undefined || parsed.steps || parsed.total)) {
        jsonPlan = parsed;
      }
    } catch(e) {}
  }

  if (jsonPlan) {
    const steps = jsonPlan.steps || [];
    let html = `<div class="rendered-plan-card">
      <div class="plan-card-header">
        <span>📋</span>
        <strong>Otonom Görev Planı (${steps.length} Adım)</strong>
      </div>
      <div class="plan-steps-list">`;
    steps.forEach((st, i) => {
      const tool = st.tool_name || st.tool || 'Araç';
      const desc = st.description || st.text || `Adım ${i+1}`;
      html += `<div class="plan-step-item">
        <span class="step-num">${i+1}</span>
        <div class="step-info">
          <div class="step-desc">${desc}</div>
          <div class="step-tool"><span class="tool-tag">⚡ ${tool}</span></div>
        </div>
      </div>`;
    });
    html += `</div></div>`;
    if (jsonPlan.message || jsonPlan.reply) {
      html += `<div style="margin-top: 8px;">${formatMarkdown(jsonPlan.message || jsonPlan.reply)}</div>`;
    }
    return html;
  }

  let esc = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  esc = esc.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  esc = esc.replace(/`([^`]+)`/g, '<code>$1</code>');
  esc = esc.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  esc = esc.replace(/\*([^*]+)\*/g, '<em>$1</em>');
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
  appendProgressCard();

  if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
    activeBotBubble = null;
    activeCursor = null;
    chatSocket.send(JSON.stringify({ message: text }));
  } else {
    // Fallback to SSE stream if websocket is offline
    sendViaSse(text);
  }
}

async function sendViaSse(text) {
  const titleText = document.getElementById('progressTitleText');
  const stepsContainer = document.getElementById('progressStepsContainer');
  try {
    const url = '/api/chat/stream?message=' + encodeURIComponent(text);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.replace(/^data: /, '').trim();
        if (!jsonStr) continue;
        try {
          const payload = JSON.parse(jsonStr);
          handleWsMessage(payload);
        } catch(err) {}
      }
    }
  } catch(err) {
    removeProgressCard();
    appendMessage(`⚠️ Hata: ${err.message}`, 'bot');
  }
}

// --- Voice Recognition & TTS ---
let voiceActive = false;
let speechRecognition = null;

function toggleVoiceInput() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    alert("Tarayıcınız Web Speech API desteklemiyor. Google Chrome veya Edge kullanın.");
    return;
  }
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!speechRecognition) {
    speechRecognition = new SpeechRec();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.lang = 'tr-TR';

    speechRecognition.onstart = () => {
      voiceActive = true;
      document.getElementById('btnMic').classList.add('recording');
    };
    speechRecognition.onresult = (e) => {
      const text = e.results[0][0].transcript;
      document.getElementById('chatInput').value = text;
      sendCurrentMessage();
    };
    speechRecognition.onend = () => {
      voiceActive = false;
      document.getElementById('btnMic').classList.remove('recording');
    };
  }

  if (voiceActive) {
    speechRecognition.stop();
  } else {
    try { speechRecognition.start(); } catch(e) { speechRecognition.stop(); }
  }
}

function speakText(text) {
  if (!('speechSynthesis' in window)) return;
  const clean = text.replace(/<[^>]+>/g, '').replace(/[*_#`]/g, '');
  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = 'tr-TR';
  utter.rate = 1.05;
  window.speechSynthesis.speak(utter);
}

// --- GraphRAG Cytoscape Visualizer ---
let cy = null;

async function loadGraphData() {
  try {
    const res = await fetch('/api/graph/data');
    const data = await res.json();
    initCytoscape(data);
  } catch(e) {
    console.error("Failed to load graph data:", e);
  }
}

function initCytoscape(graphData) {
  const container = document.getElementById('cyGraph');
  if (!container) return;

  const elements = [];
  (graphData.nodes || []).forEach(n => {
    elements.push({
      group: 'nodes',
      data: { id: n.id, label: n.label || n.id }
    });
  });
  (graphData.edges || []).forEach(e => {
    elements.push({
      group: 'edges',
      data: { id: e.id, source: e.source, target: e.target, label: e.label || '' }
    });
  });

  if (cy) {
    cy.destroy();
  }

  cy = cytoscape({
    container: container,
    elements: elements,
    style: [
      {
        selector: 'node',
        style: {
          'label': 'data(label)',
          'color': '#F8FAFC',
          'background-color': '#00F0FF',
          'font-size': '11px',
          'font-family': 'Plus Jakarta Sans',
          'text-valign': 'bottom',
          'text-margin-y': 6,
          'width': 28,
          'height': 28,
          'border-width': 2,
          'border-color': '#8B5CF6',
          'overlay-opacity': 0
        }
      },
      {
        selector: 'edge',
        style: {
          'width': 1.5,
          'line-color': 'rgba(0, 240, 255, 0.4)',
          'target-arrow-color': '#00F0FF',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(label)',
          'font-size': '9px',
          'color': '#94A3B8',
          'text-rotation': 'autorotate',
          'text-margin-y': -6
        }
      },
      {
        selector: ':selected',
        style: {
          'background-color': '#00FF9D',
          'border-color': '#FFFFFF',
          'border-width': 3,
          'line-color': '#00FF9D',
          'target-arrow-color': '#00FF9D'
        }
      }
    ],
    layout: {
      name: 'cose',
      animate: true,
      animationDuration: 500,
      padding: 30
    }
  });

  cy.on('tap', 'node', function(evt) {
    const node = evt.target;
    const drawer = document.getElementById('graphDrawer');
    const drawerTitle = document.getElementById('drawerTitle');
    const drawerBody = document.getElementById('drawerBody');
    drawer.style.display = 'flex';
    drawerTitle.textContent = `📌 ${node.data('label')}`;
    const connectedEdges = node.connectedEdges();
    drawerBody.innerHTML = `Bağlantılı ilişkiler: <strong>${connectedEdges.length}</strong><br>` +
      connectedEdges.map(e => `• ${e.data('source')} ➔ <em>${e.data('label')}</em> ➔ ${e.data('target')}`).join('<br>');
  });

  cy.on('tap', function(evt) {
    if (evt.target === cy) {
      document.getElementById('graphDrawer').style.display = 'none';
    }
  });
}

function fitGraph() {
  if (cy) cy.fit(null, 30);
}

// --- Process Manager ---
let allProcesses = [];

async function loadProcesses() {
  try {
    const res = await fetch('/api/system/processes?limit=30');
    allProcesses = await res.json();
    renderProcesses(allProcesses);
  } catch(e) {
    console.error("Failed to load processes:", e);
  }
}

function renderProcesses(procs) {
  const tbody = document.getElementById('procTableBody');
  tbody.innerHTML = '';
  if (!procs || procs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 20px; color: var(--text-muted);">Süreç bulunamadı.</td></tr>';
    return;
  }
  procs.forEach(p => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="pid-tag">${p.pid}</td>
      <td class="proc-name">${p.name}</td>
      <td><span style="color: ${p.cpu > 20 ? 'var(--accent-rose)' : 'var(--text-primary)'}">${p.cpu}%</span></td>
      <td>${p.ram}%</td>
      <td>
        <button class="btn-kill" onclick="killProcess(${p.pid}, '${p.name}')">Sonlandır</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function filterProcesses() {
  const query = document.getElementById('procSearchInput').value.toLowerCase().trim();
  const filtered = allProcesses.filter(p => p.name.toLowerCase().includes(query) || String(p.pid).includes(query));
  renderProcesses(filtered);
}

async function killProcess(pid, name) {
  if (!confirm(`'${name}' (PID: ${pid}) sürecini sonlandırmak istediğinizden emin misiniz?`)) return;
  try {
    const res = await fetch('/api/system/kill-process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid })
    });
    const data = await res.json();
    if (data.success) {
      loadProcesses();
    } else {
      alert(`Sonlandırma hatası: ${data.error || 'İşlem engellendi'}`);
    }
  } catch(e) {
    alert(`Bağlantı hatası: ${e.message}`);
  }
}

// --- Memory Stats Telemetry ---
async function fetchMemoryStats() {
  try {
    const res = await fetch('/api/memory/stats');
    const data = await res.json();
    document.getElementById('statMemDocs').textContent = data.total_documents;
    document.getElementById('statGraphNodes').textContent = data.graph_nodes;
    document.getElementById('statGraphEdges').textContent = data.graph_edges;
  } catch(e) {}
}

// --- Live Telemetry & Status ---
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const d = await res.json();
    document.getElementById('headerProviderModel').textContent = `${d.provider} | ${d.model}`;
    const modeNames = { full: "🔓 TAM YETKİ", safe: "🔐 GÜVENLİ MOD", ask: "🔒 SORARAK ONAY" };
    document.getElementById('headerAuthority').textContent = modeNames[d.approval_mode] || d.approval_mode;

    document.querySelectorAll('.radio-option').forEach(el => el.classList.remove('selected'));
    const opt = document.getElementById('opt-' + d.approval_mode);
    if (opt) {
      opt.classList.add('selected');
      const radio = opt.querySelector('input');
      if (radio) radio.checked = true;
    }
  } catch(e) {}
}

async function fetchSysinfo() {
  try {
    const res = await fetch('/api/sysinfo');
    const d = await res.json();
    document.getElementById('txtCpuUsage').textContent = d.cpu_percent + '%';
    document.getElementById('barCpu').style.width = Math.min(100, d.cpu_percent) + '%';
    document.getElementById('txtRamUsage').textContent = `${d.ram_percent}% (${d.ram_used_gb} / ${d.ram_total_gb} GB)`;
    document.getElementById('barRam').style.width = Math.min(100, d.ram_percent) + '%';
  } catch(e) {}
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
  } catch(e) {}
}

let allTools = [];

async function loadTools() {
  try {
    const res = await fetch('/api/tools');
    allTools = await res.json();
    renderTools(allTools);
  } catch(e) {}
}

function renderTools(tools) {
  const container = document.getElementById('toolListContainer');
  container.innerHTML = '';
  tools.forEach(t => {
    const card = document.createElement('div');
    card.className = 'tool-item-card';
    card.innerHTML = `
      <div class="tool-item-name">⚡ ${t.name}</div>
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

function toggleLanguage() {
  const btn = document.getElementById('btnLangToggle');
  btn.textContent = btn.textContent.includes('TR') ? '🇺🇸 EN' : '🇹🇷 TR';
}

// Auto-run on load
initWebSocket();
fetchStatus();
fetchSysinfo();
fetchMemoryStats();
loadModels();
loadTools();
setInterval(fetchStatus, 4000);
setInterval(fetchSysinfo, 2500);
setInterval(fetchMemoryStats, 8000);

// Auto-refresh Process Manager when view is active
let processRefreshTimer = null;
const originalSwitchView = switchView;
switchView = function(viewId) {
  originalSwitchView(viewId);
  if (processRefreshTimer) { clearInterval(processRefreshTimer); processRefreshTimer = null; }
  if (viewId === 'processes') {
    loadProcesses();
    processRefreshTimer = setInterval(loadProcesses, 3000);
  }
};
</script>
</body>
</html>
"""


def _write_to_stderr(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
