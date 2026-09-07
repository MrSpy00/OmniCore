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
import secrets as _secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
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
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_DASHBOARD_EPHEMERAL_KEY: str | None = None
# SECURITY: Track active WebSocket sessions for proper cleanup
_ws_sessions: set[Any] = set()
_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<circle cx="16" cy="16" r="14" fill="#07090E" stroke="#00F0FF" stroke-width="2"/>'
    '<path d="M10 16 L16 10 L22 16 L16 22 Z" fill="#00F0FF"/>'
    "</svg>"
)


def _get_dashboard_key() -> str:
    """Return dashboard API key (env DASHBOARD_API_KEY or ephemeral)."""
    global _DASHBOARD_EPHEMERAL_KEY
    import os

    configured = os.environ.get("DASHBOARD_API_KEY", "").strip()
    if configured:
        return configured
    if _DASHBOARD_EPHEMERAL_KEY is None:
        _DASHBOARD_EPHEMERAL_KEY = _secrets.token_urlsafe(32)
        logger.warning(
            "dashboard.no_api_key_ephemeral_generated",
            hint="Set DASHBOARD_API_KEY for persistent access",
        )
    return _DASHBOARD_EPHEMERAL_KEY


_shared_graph_memory: Any = None
_graph_memory_lock = asyncio.Lock()


async def _get_graph_memory() -> Any:
    global _shared_graph_memory
    if _router and getattr(_router, "_graph_memory", None) is not None:
        return _router._graph_memory
    if _shared_graph_memory is None:
        async with _graph_memory_lock:
            if _shared_graph_memory is None:
                try:
                    from memory.graph_memory import GraphMemory

                    gm = GraphMemory()
                    await gm.initialize()
                    _shared_graph_memory = gm
                except Exception as exc:
                    logger.warning("dashboard.graph_memory_init_failed", error=str(exc))
                    return None
    return _shared_graph_memory


def _is_client_authorized(client_host: str, auth_header: str = "", query_token: str | None = None) -> bool:
    import os

    require_auth = os.environ.get("DASHBOARD_REQUIRE_AUTH", "0").lower() in ("1", "true", "yes")
    expected = _get_dashboard_key()
    provided = ""
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:].strip()
    elif query_token:
        provided = query_token.strip()

    if provided and _secrets.compare_digest(provided, expected):
        return True
    if not require_auth and client_host in ("127.0.0.1", "localhost", "::1", "testclient"):
        return True
    return False


def set_router(router: CognitiveRouter) -> None:
    global _router
    _router = router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    global _shared_graph_memory
    if _shared_graph_memory is not None:
        try:
            await _shared_graph_memory.close()
        except Exception:
            pass
        _shared_graph_memory = None


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="OmniCore Dashboard 2.0", docs_url="/api/docs", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
        allow_origins=[
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "img-src 'self' data: https:; "
            "connect-src 'self' ws: wss: http: https:;"
        )
        return response

    async def verify_dashboard_auth(authorization: str = Header(default="")):
        """Verify API key for sensitive dashboard endpoints."""
        from fastapi import HTTPException

        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization[7:].strip()
        if not _secrets.compare_digest(token, _get_dashboard_key()):
            raise HTTPException(status_code=403, detail="Invalid API key")

    @app.get("/api/auth/token")
    async def api_auth_token(request: Request):
        """Return ephemeral dashboard token for authorized local client."""
        client_host = request.client.host if request.client else "127.0.0.1"
        if client_host not in ("127.0.0.1", "localhost", "::1", "testclient"):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        return {"token": _get_dashboard_key()}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return get_dashboard_html()

    @app.get("/favicon.ico")
    @app.get("/favicon.png")
    async def favicon():
        fav_path = _ASSETS_DIR / "OmniCore-bounce.png"
        if fav_path.exists():
            return FileResponse(fav_path, media_type="image/png")
        return Response(content=_FAVICON_SVG, media_type="image/svg+xml")

    @app.get("/assets/{filename}")
    async def get_asset(filename: str):
        asset_file = (_ASSETS_DIR / filename).resolve()
        assets_dir_resolved = _ASSETS_DIR.resolve()
        if not asset_file.is_relative_to(assets_dir_resolved):
            return Response(status_code=403)
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
        gm = await _get_graph_memory()
        if gm:
            try:
                data = await gm.export_graph_data()
                nodes_count = len(data.get("nodes", []))
                edges_count = len(data.get("edges", []))
            except Exception:
                pass
        return {
            "total_documents": doc_count,
            "graph_nodes": nodes_count,
            "graph_edges": edges_count,
        }

    @app.get("/api/chat/stream")
    async def api_chat_stream(request: Request, message: str = Query(...)):
        client_host = request.client.host if request.client else "127.0.0.1"
        auth_hdr = request.headers.get("Authorization", "")
        token = request.query_params.get("token")
        if not _is_client_authorized(client_host, auth_hdr, token):
            return JSONResponse({"error": "Unauthorized access"}, status_code=401)

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
        client_host = request.client.host if request.client else "127.0.0.1"
        auth_hdr = request.headers.get("Authorization", "")
        if not _is_client_authorized(client_host, auth_hdr):
            return JSONResponse({"error": "Unauthorized access"}, status_code=401)

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
        gm = await _get_graph_memory()
        if gm:
            try:
                return await gm.export_graph_data()
            except Exception as exc:
                logger.error("dashboard.graph_data_error", error=str(exc))
                return {"nodes": [], "edges": [], "count": 0, "error": str(exc)}
        return {"nodes": [], "edges": [], "count": 0}

    @app.get("/api/system/processes", dependencies=[Depends(verify_dashboard_auth)])
    async def api_system_processes(limit: int = 25):
        """Return top system processes sorted by CPU and memory consumption."""
        import psutil

        procs: list[dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = p.info
                if info.get("name"):
                    procs.append(
                        {
                            "pid": info["pid"],
                            "name": info["name"],
                            "cpu": round(info.get("cpu_percent") or 0.0, 1),
                            "ram": round(info.get("memory_percent") or 0.0, 1),
                        }
                    )
            except Exception:
                pass
        procs.sort(key=lambda x: (x["cpu"], x["ram"]), reverse=True)
        return procs[:limit]

    @app.post("/api/system/kill-process", dependencies=[Depends(verify_dashboard_auth)])
    async def api_system_kill_process(request: Request):
        """Terminate a process by PID with safety validation."""
        import os

        import psutil

        body = await request.json()
        pid = body.get("pid")
        if not pid:
            return JSONResponse({"error": "Missing pid parameter"}, status_code=400)
        try:
            pid_int = int(pid)
            if pid_int in (0, 4, os.getpid(), os.getppid()):
                return JSONResponse(
                    {"error": "Kritik veya ana OmniCore sürecini sonlandırma engellendi."},
                    status_code=403,
                )
            p = psutil.Process(pid_int)
            name = p.name().lower()
            critical_names = {
                "system",
                "system idle process",
                "smss.exe",
                "csrss.exe",
                "wininit.exe",
                "services.exe",
                "lsass.exe",
                "svchost.exe",
                "init",
                "systemd",
                "launchd",
            }
            if name in critical_names:
                return JSONResponse(
                    {"error": f"Sistem kritik süreci '{name}' sonlandırılamaz."},
                    status_code=403,
                )
            p.terminate()
            return {"success": True, "message": f"Süreç '{p.name()}' (PID: {pid_int}) sonlandırıldı."}
        except psutil.NoSuchProcess:
            return JSONResponse({"error": f"PID {pid} bulunamadı."}, status_code=404)
        except psutil.AccessDenied:
            return JSONResponse({"error": f"PID {pid} sonlandırmak için yetki yetersiz."}, status_code=403)
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @app.websocket("/ws/chat")
    async def ws_chat(websocket: WebSocket):
        """Bidirectional WebSocket for real-time streaming chat with typewriter effect.

        SECURITY: Includes proper cleanup, timeout, and error handling to prevent resource leaks.
        """
        client_host = websocket.client.host if websocket.client else "127.0.0.1"
        token = websocket.query_params.get("token")
        auth_hdr = websocket.headers.get("Authorization", "")
        if not _is_client_authorized(client_host, auth_hdr, token):
            await websocket.close(code=1008)
            return

        await websocket.accept()
        _ws_sessions.add(websocket)
        try:
            while True:
                # SECURITY: Add timeout to prevent zombie connections
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=300.0)
                except TimeoutError:
                    # Send ping to check if client is still alive
                    try:
                        await websocket.send_text(json.dumps({"type": "ping"}))
                        continue
                    except Exception:
                        break

                try:
                    payload = json.loads(data)
                    # Handle pong response
                    if payload.get("type") == "pong":
                        continue
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
                    await websocket.send_text(json.dumps({"type": "done", "reply": reply}, ensure_ascii=False))
                except Exception as exc:
                    logger.error("dashboard.ws_error", error=str(exc))
                    try:
                        await websocket.send_text(json.dumps({"type": "error", "error": str(exc)}))
                    except Exception:
                        break
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.error("dashboard.ws_unexpected_error", error=str(exc))
        finally:
            # SECURITY: Always clean up the session
            _ws_sessions.discard(websocket)

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

    @app.post("/api/config", dependencies=[Depends(verify_dashboard_auth)])
    async def api_config(request: Request):
        body = await request.json()
        from config.live_config import get_live_config

        lc = get_live_config()
        key = body.get("key", "")
        value = body.get("value", "")
        if key and value:
            ok, msg = lc.set(key, value)
            if ok and _router:
                if key in ("provider", "model", "groq_primary_model", "omni_llm_model"):
                    try:
                        await _router.rebuild_llm()
                    except Exception as e:
                        logger.warning("dashboard.rebuild_llm_failed", error=str(e))
                elif key == "approval_mode" and hasattr(_router, "_guardian"):
                    mode_map = {"full": "yes", "safe": "safe", "ask": "ask"}
                    mapped_mode = mode_map.get(value, value)
                    _router._guardian.set_mode(mapped_mode)
            return {"success": ok, "message": msg}
        return JSONResponse({"error": "Missing key/value"}, status_code=400)

    @app.get("/api/sysinfo")
    @app.get("/api/system-info")
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


_dashboard_html_cache: str | None = None


def get_dashboard_html() -> str:
    global _dashboard_html_cache
    if _dashboard_html_cache is None:
        tpl_path = _TEMPLATES_DIR / "dashboard.html"
        if tpl_path.exists():
            _dashboard_html_cache = tpl_path.read_text(encoding="utf-8")
        else:
            _dashboard_html_cache = "<!DOCTYPE html><html><body><h1>OmniCore Dashboard</h1></body></html>"
    return _dashboard_html_cache


def __getattr__(name: str) -> Any:
    if name == "DASHBOARD_HTML":
        return get_dashboard_html()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
