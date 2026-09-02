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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config.logging import get_logger
from config.settings import get_settings
from core.router import CognitiveRouter
from models.messages import Message, MessageRole

logger = get_logger(__name__)

# Will be set by run.py
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
            return {"reply": f"Hata: {type(exc).__name__}", "status": "error"}

    @app.get("/api/models")
    async def api_models():
        from config.settings import get_available_models
        return get_available_models()

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

    @app.get("/api/telemetry")
    async def api_telemetry():
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": cpu,
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
        }

    return app


# Embedded dashboard HTML - single file, no external deps
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniCore Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0a0f;--surface:#12121a;--surface2:#1a1a25;--surface3:#22222f;
  --border:#2a2a3a;--text:#e0e0e0;--text2:#8888aa;
  --accent:#6c5ce7;--accent2:#a855f7;--accent3:#3b82f6;
  --success:#10b981;--warning:#f59e0b;--error:#ef4444;
  --glow:0 0 20px rgba(108,92,231,0.3);
}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden}
.app{display:grid;grid-template-columns:280px 1fr 300px;grid-template-rows:60px 1fr;height:100vh}

/* Header */
.header{grid-column:1/-1;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;gap:16px;z-index:10}
.header .logo{font-size:20px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header .status{display:flex;gap:12px;margin-left:auto;align-items:center}
.header .dot{width:8px;height:8px;border-radius:50%;background:var(--success);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* Sidebar */
.sidebar{background:var(--surface);border-right:1px solid var(--border);padding:16px;overflow-y:auto}
.sidebar h3{color:var(--text2);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:16px 0 8px}
.sidebar .nav-item{padding:10px 12px;border-radius:8px;cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:10px;font-size:14px}
.sidebar .nav-item:hover{background:var(--surface2)}
.sidebar .nav-item.active{background:linear-gradient(135deg,rgba(108,92,231,.2),rgba(168,85,247,.15));border:1px solid rgba(108,92,231,.3)}
.nav-icon{width:20px;text-align:center;font-size:16px}

/* Main chat */
.main{display:flex;flex-direction:column;background:var(--bg)}
.messages{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px}
.msg{max-width:80%;padding:12px 16px;border-radius:12px;font-size:14px;line-height:1.5;animation:fadeIn .3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.msg.user{align-self:flex-end;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;border-bottom-right-radius:4px}
.msg.bot{align-self:flex-start;background:var(--surface2);border:1px solid var(--border);border-bottom-left-radius:4px}
.msg.system{align-self:center;background:var(--surface3);color:var(--text2);font-size:12px;padding:6px 12px;border-radius:20px}
.typing{display:flex;gap:4px;padding:12px 16px}
.typing span{width:6px;height:6px;background:var(--text2);border-radius:50%;animation:typing .8s infinite}
.typing span:nth-child(2){animation-delay:.2s}
.typing span:nth-child(3){animation-delay:.4s}
@keyframes typing{0%,100%{opacity:.3;transform:translateY(0)}50%{opacity:1;transform:translateY(-4px)}}

/* Input area */
.input-area{padding:16px 20px;background:var(--surface);border-top:1px solid var(--border);display:flex;gap:12px;align-items:center}
.input-area textarea{flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:12px 16px;color:var(--text);font-size:14px;resize:none;height:44px;max-height:120px;font-family:inherit;transition:border .2s}
.input-area textarea:focus{outline:none;border-color:var(--accent)}
.btn{padding:10px 20px;border:none;border-radius:10px;cursor:pointer;font-size:14px;font-weight:600;transition:all .2s;display:flex;align-items:center;gap:6px}
.btn-primary{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;box-shadow:var(--glow)}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 0 30px rgba(108,92,231,.4)}
.btn-primary:active{transform:translateY(0)}
.btn-voice{background:var(--surface2);border:1px solid var(--border);color:var(--text);width:44px;height:44px;border-radius:50%;justify-content:center;font-size:18px}
.btn-voice.recording{background:var(--error);border-color:var(--error);animation:recPulse 1s infinite}
@keyframes recPulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,.4)}50%{box-shadow:0 0 0 12px rgba(239,68,68,0)}}

/* Right panel */
.panel{background:var(--surface);border-left:1px solid var(--border);padding:16px;overflow-y:auto}
.panel h3{color:var(--text2);font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:12px 0 8px}
.card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:10px}
.card .label{color:var(--text2);font-size:11px;margin-bottom:4px}
.card .value{font-size:14px;font-weight:600}
.card .value.ok{color:var(--success)}
.card .value.warn{color:var(--warning)}

/* Telemetry bars */
.bar-container{margin:8px 0}
.bar-label{display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px}
.bar{height:6px;background:var(--surface3);border-radius:3px;overflow:hidden}
.bar-fill{height:100%;border-radius:3px;transition:width .5s ease;background:linear-gradient(90deg,var(--accent),var(--accent2))}

/* Model selector */
.model-select{width:100%;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;color:var(--text);font-size:13px;margin-top:4px}
.model-select:focus{outline:none;border-color:var(--accent)}

/* Quick actions */
.quick-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.quick-btn{padding:6px 10px;background:var(--surface3);border:1px solid var(--border);border-radius:6px;color:var(--text2);font-size:11px;cursor:pointer;transition:all .2s}
.quick-btn:hover{border-color:var(--accent);color:var(--text)}

/* Scrollbar */
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--text2)}

/* Responsive */
@media(max-width:900px){
  .app{grid-template-columns:1fr;grid-template-rows:60px 1fr}
  .sidebar,.panel{display:none}
}
</style>
</head>
<body>
<div class="app">
  <header class="header">
    <div class="logo">OMNICORE</div>
    <div class="status">
      <div class="dot" id="statusDot"></div>
      <span id="statusText" style="font-size:13px;color:var(--text2)">Connecting...</span>
    </div>
  </header>

  <aside class="sidebar">
    <div class="nav-item active" onclick="showView('chat')">
      <span class="nav-icon">&#x1F4AC;</span> Sohbet
    </div>
    <div class="nav-item" onclick="showView('settings')">
      <span class="nav-icon">&#x2699;</span> Ayarlar
    </div>
    <div class="nav-item" onclick="showView('telemetry')">
      <span class="nav-icon">&#x1F4CA;</span> Telemetri
    </div>

    <h3>Hizli Komutlar</h3>
    <div class="quick-actions">
      <div class="quick-btn" onclick="sendQuick('/status')">/status</div>
      <div class="quick-btn" onclick="sendQuick('/models')">/models</div>
      <div class="quick-btn" onclick="sendQuick('/doctor')">/doctor</div>
      <div class="quick-btn" onclick="sendQuick('/reset')">/reset</div>
      <div class="quick-btn" onclick="sendQuick('/config')">/config</div>
      <div class="quick-btn" onclick="sendQuick('/help')">/help</div>
    </div>
  </aside>

  <main class="main">
    <div class="messages" id="messages">
      <div class="msg system">OmniCore Dashboard'a ho\u015F geldiniz</div>
    </div>
    <div class="input-area">
      <button class="btn btn-voice" id="voiceBtn" onclick="toggleVoice()" title="Sesli konusma">
        &#x1F3A4;
      </button>
      <textarea id="chatInput" placeholder="Mesajinizi yazin..." rows="1"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage()}"></textarea>
      <button class="btn btn-primary" onclick="sendMessage()">
        Gonder &#x27A4;
      </button>
    </div>
  </main>

  <aside class="panel" id="rightPanel">
    <h3>Sistem Durumu</h3>
    <div class="card">
      <div class="label">Provider</div>
      <div class="value ok" id="pProvider">-</div>
    </div>
    <div class="card">
      <div class="label">Model</div>
      <div class="value" id="pModel">-</div>
    </div>
    <div class="card">
      <div class="label">Araclar</div>
      <div class="value" id="pTools">-</div>
    </div>
    <div class="card">
      <div class="label">Onay Modu</div>
      <div class="value" id="pApproval">-</div>
    </div>
    <div class="card">
      <div class="label">Uptime</div>
      <div class="value" id="pUptime">-</div>
    </div>

    <h3>Telemetri</h3>
    <div class="card">
      <div class="bar-label"><span>CPU</span><span id="cpuVal">0%</span></div>
      <div class="bar"><div class="bar-fill" id="cpuBar" style="width:0%"></div></div>
    </div>
    <div class="card">
      <div class="bar-label"><span>RAM</span><span id="ramVal">0%</span></div>
      <div class="bar"><div class="bar-fill" id="ramBar" style="width:0%"></div></div>
    </div>

    <h3>Model Sec</h3>
    <select class="model-select" id="modelSelect" onchange="changeModel(this.value)">
      <option>Yukleniyor...</option>
    </select>
  </aside>
</div>

<script>
const msgEl = document.getElementById('messages');
const inputEl = document.getElementById('chatInput');
let isRecording = false;

function addMsg(text, type='bot') {
  const d = document.createElement('div');
  d.className = 'msg ' + type;
  d.textContent = text;
  msgEl.appendChild(d);
  msgEl.scrollTop = msgEl.scrollHeight;
}

function addTyping() {
  const d = document.createElement('div');
  d.className = 'typing';
  d.id = 'typing';
  d.innerHTML = '<span></span><span></span><span></span>';
  msgEl.appendChild(d);
  msgEl.scrollTop = msgEl.scrollHeight;
}

function removeTyping() {
  const t = document.getElementById('typing');
  if (t) t.remove();
}

let recognition = null;
let speechSynthVoice = null;
let voiceOutputEnabled = false;

if ('speechSynthesis' in window) {
  window.speechSynthesis.onvoiceschanged = () => {
    const voices = window.speechSynthesis.getVoices();
    speechSynthVoice = voices.find(v => v.lang.startsWith('tr')) || voices[0];
  };
}

function speakReply(text) {
  if (!window.speechSynthesis) return;
  const clean = text.replace(/[*_#`~\[\]]/g, '').replace(/http\S+/g, '');
  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = 'tr-TR';
  if (speechSynthVoice) utter.voice = speechSynthVoice;
  window.speechSynthesis.speak(utter);
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = '';
  addMsg(text, 'user');
  addTyping();
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    removeTyping();
    addMsg(data.reply || 'No response', 'bot');
    if (voiceOutputEnabled) {
      speakReply(data.reply);
    }
  } catch(e) {
    removeTyping();
    addMsg('Hata: ' + e.message, 'system');
  }
}

function sendQuick(cmd) {
  inputEl.value = cmd;
  sendMessage();
}

function initSpeechRecognition() {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRec) {
    addMsg('Tarayıcınız Web Speech API ses tanımayı desteklemiyor. Lütfen Chrome, Edge veya Brave kullanın.', 'system');
    return null;
  }
  const rec = new SpeechRec();
  rec.lang = 'tr-TR';
  rec.interimResults = true;
  rec.continuous = false;

  rec.onstart = () => {
    isRecording = true;
    voiceOutputEnabled = true;
    document.getElementById('voiceBtn').classList.add('recording');
    addMsg('🎙️ Mikrofon dinleniyor... Konuşun (Sözünüz bitince otomatik gönderilecek)', 'system');
  };

  rec.onresult = (event) => {
    let finalTranscript = '';
    let interimTranscript = '';
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }
    inputEl.value = finalTranscript || interimTranscript;
    if (finalTranscript) {
      sendMessage();
    }
  };

  rec.onerror = (event) => {
    addMsg('Mikrofon bildirimi: ' + (event.error === 'no-speech' ? 'Ses algılanamadı.' : event.error), 'system');
    isRecording = false;
    document.getElementById('voiceBtn').classList.remove('recording');
  };

  rec.onend = () => {
    isRecording = false;
    document.getElementById('voiceBtn').classList.remove('recording');
  };

  return rec;
}

function toggleVoice() {
  if (!recognition) {
    recognition = initSpeechRecognition();
    if (!recognition) return;
  }
  if (isRecording) {
    recognition.stop();
  } else {
    try {
      recognition.start();
    } catch(e) {
      recognition.stop();
    }
  }
}

async function refreshStatus() {
  try {
    const res = await fetch('/api/status');
    const d = await res.json();
    document.getElementById('pProvider').textContent = d.provider;
    document.getElementById('pModel').textContent = d.model;
    document.getElementById('pTools').textContent = d.tools;
    document.getElementById('pApproval').textContent = d.approval_mode;
    const h = Math.floor(d.uptime_seconds/3600);
    const m = Math.floor((d.uptime_seconds%3600)/60);
    document.getElementById('pUptime').textContent = h+'s '+m+'d';
    document.getElementById('statusText').textContent = d.provider + ' | ' + d.model;
  } catch(e) {}
}

async function refreshTelemetry() {
  try {
    const res = await fetch('/api/telemetry');
    const d = await res.json();
    document.getElementById('cpuVal').textContent = d.cpu_percent + '%';
    document.getElementById('cpuBar').style.width = d.cpu_percent + '%';
    document.getElementById('ramVal').textContent = d.ram_percent + '% (' + d.ram_used_gb + '/' + d.ram_total_gb + ' GB)';
    document.getElementById('ramBar').style.width = d.ram_percent + '%';
  } catch(e) {}
}

async function loadModels() {
  try {
    const res = await fetch('/api/models');
    const d = await res.json();
    const sel = document.getElementById('modelSelect');
    sel.innerHTML = '';
    for (const [prov, models] of Object.entries(d)) {
      const grp = document.createElement('optgroup');
      grp.label = prov.toUpperCase();
      for (const m of models) {
        const opt = document.createElement('option');
        opt.value = prov + ':' + m.id;
        opt.textContent = m.name + ' (' + m.context + ')';
        grp.appendChild(opt);
      }
      sel.appendChild(grp);
    }
  } catch(e) {}
}

async function changeModel(val) {
  const [prov, model] = val.split(':');
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({key:'model', value:model})
  });
  await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({key:'provider', value:prov})
  });
  addMsg('Model degistirildi: ' + model, 'system');
  refreshStatus();
}

function showView(v) {
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  event.currentTarget.classList.add('active');
}

// Auto-refresh
refreshStatus();
loadModels();
setInterval(refreshStatus, 5000);
setInterval(refreshTelemetry, 3000);
</script>
</body>
</html>"""


def _write_to_stderr(msg: str) -> None:
    import sys
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
