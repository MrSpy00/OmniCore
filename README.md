# OmniCore v0.40.0 — The Sovereign Enterprise AI OS

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![Build Status](https://img.shields.io/badge/Tests-141%20Passed-brightgreen.svg)
![Async Hygiene](https://img.shields.io/badge/Async%20Audit-0%20Issues-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-black.svg)

**OmniCore** is a production-grade, enterprise-ready autonomous cognitive OS assistant framework. It bridges local system administration, Model Context Protocol (MCP) server integration, self-healing code refactoring, universal database exploration, headless browser automation, hardware telemetry inspection, multi-agent subagent swarms, cyberpunk terminal HUD telemetry, real-time duplex voice streaming, security audit toolkits, self-improving skill creation, knowledge graph memory (GraphRAG), continuous background daemons, local Ollama offline fallback, kernel privilege triage, multi-drive file search, Steam/Epic game engine updating, web/GUI automation, and multi-provider LLM orchestration (Gemini, Groq & Ollama).

---

## 🌟 English Overview

OmniCore combines **User-Facing Capabilities** (voice loop, EdgeTTS speech, PyAudio listening, Steam & Epic launcher management, 2-stage categorized memory, Self-Improving Skill Curator, Cyberpunk Terminal Telemetry HUD) with **Kernel & OS Dominance Layer** (Enterprise MCP Server Gateway, Self-Healing Code Refactorer, Universal Database Explorer, Headless Browser Automation, Hardware & Thermal Telemetry, Multi-Agent Swarm Protocol, Security Audit & Red Team Toolkit, Knowledge Graph Memory, Continuous Background Event Daemons, Offline Ollama Fallback, NTFS `$MFT` / Everything `es.exe` instant file search, privilege triage via `whoami /priv` & `id`, LOLBins execution safety, and 4-tier risk governance).

### Key Features

- 🔌 **Enterprise MCP Gateway**: Expose OmniCore's 45+ toolkits to external tools and IDEs (Claude Desktop, Zed, Cursor, VS Code) via JSON-RPC 2.0 (`interfaces/mcp_gateway.py`).
- 🛠️ **Self-Healing Code Refactorer**: AST Python code complexity analysis (`refactor_analyze_file`) and automated unified diff patch generation (`refactor_generate_patch`).
- 🗄️ **Universal Database Explorer**: Introspect SQLite database schemas, columns, and data types (`db_inspect_schema`) and execute safe SQL queries (`db_query_execute`).
- 🌐 **Headless Browser Automation**: Fetch web page content with clean text extraction (`browser_fetch_page`) and take screen captures (`browser_take_screenshot`).
- 💻 **Hardware Telemetry Inspector**: Real-time CPU, GPU VRAM utilization, battery status, thermal sensors, and disk I/O metrics inspection (`hardware_inspect_telemetry`).
- 🐝 **Multi-Agent Subagent Swarm Protocol**: Spawn specialized, parallel background subagents (`swarm_spawn_agent`, `swarm_list_agents`, `swarm_collect_results`) that execute tasks concurrently and aggregate findings.
- 🎛️ **Cyberpunk Terminal Telemetry HUD**: Interactive CLI telemetry dashboard (`interfaces/hud.py`) displaying live LLM routes, graph node metrics, active daemons, CPU/RAM bars, and tool usage.
- 🎙️ **Real-Time Duplex Voice Engine**: Low-latency WebSocket streaming audio engine (`interfaces/voice_duplex.py`) for instantaneous conversational interactions.
- 🛡️ **Security Audit & Red Team Toolkit**: Asynchronous port scanning (`security_port_scan`), system security posture audit (`security_audit_system`), and CVE advisory lookups (`security_cve_lookup`).
- 🌐 **Unified OS Platform Adapter**: Cross-platform system abstraction layer (`core/platform_adapter.py`) unifying Windows PowerShell/Win32 APIs, Linux Bash/systemd, and macOS launchd.
- 🧠 **Cognitive Router & Failover**: Automatic multi-provider failover (Gemini 2.0 Flash / Pro, Groq Llama 3.3 70B & Local Ollama offline fallback) with count-based circuit breaker and semantic tool pruning.
- ⚡ **Self-Improving Skill Curator**: Synthesize new Python tool classes dynamically at runtime (`skill_create`, `skill_list`, `skill_execute`) saved to `workspace/skills/`.
- 🕸️ **Knowledge Graph Memory Engine**: GraphRAG entity-relation memory store (`memory/graph_memory.py`) connecting entities (`User -> owns -> OmniCore -> uses -> ChromaDB`) for multi-hop reasoning.
- 🔄 **Continuous Background Daemon & Event Reactor**: Asynchronous directory watchers, resource limit alerts (CPU/RAM > 90%), and event reactors running in the background.
- 📴 **Local Ollama Offline Fallback**: Zero-internet offline capability automatically routing to local Ollama / LM Studio instances (`http://localhost:11434/v1`).
- 💾 **2-Stage Categorized Persistent Memory**: Automatic filtering and structured JSON categorization (`identity`, `preferences`, `projects`, `relationships`, `wishes`, `notes`) with dynamic system prompt injection.
- 🎮 **Steam & Epic Game Engine Updater**: Multi-drive `libraryfolders.vdf` and `appmanifest_*.acf` parsing for Steam, Epic `Manifests/*.item` discovery, automated updates, and optional post-update auto-shutdown.
- 🖥️ **Hybrid GUI Window Inspector**: Desktop window inspection (`gui_inspect_windows`, `gui_focus_window`) bringing target app windows to foreground for precise GUI interaction.
- ⚡ **Non-Blocking Async Architecture**: 100% async-native execution verified with zero blocking IO calls on main event loop threads.
- 🛡️ **4-Tier Capability Policy Governance**: Enforces `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` risk tiers with pre-action dry-run simulations, double confirmation for destructive actions, and sensitive data redaction.

---

## 🇹🇷 Türkçe Özeti

**OmniCore**, işletim sistemi düzeyinde mutlak hakimiyet ve otonom otomasyon sağlayan yapay zeka tabanlı bir asistan mimarisidir. Kullanıcı katmanındaki sesli etkileşim (EdgeTTS, PyAudio), oyun motoru yönetimi (Steam/Epic), otonom hafıza ve çok adımlı görev planlama yeteneklerini, sistem katmanındaki raw $MFT disk tarama, token/yetki denetimi (`whoami /priv`), LOLBins güvenliği ve 4-seviyeli risk yönetimi ile birleştirir.

---

## 🏗️ Core Architecture / Çekirdek Mimari

```mermaid
flowchart TD
    User[User Request / Voice Input] --> Router[Cognitive Router]
    Router --> Policy{Guardian & 4-Tier Policy}
    Policy -- Safe --> Memory[2-Stage Memory Pipeline]
    Policy -- Approvals --> HITL[Human-In-The-Loop Approval]
    HITL -- Approved --> Memory
    Memory --> ToolReg[Tool Registry]
    
    subgraph Toolkits [OmniCore Toolkits (40+ Toolkits)]
        T1[OS & System Kernel]
        T2[Fast $MFT Disk Search]
        T3[Steam & Epic Game Updater]
        T4[Voice Loop & EdgeTTS]
        T5[Developer & Web Automation]
    end
    
    ToolReg --> Toolkits
    Toolkits --> Exec[Host OS Execution]
    Exec --> Recovery[Self-Healing Recovery Engine]
    Recovery --> Res[Final Spoken & Visual Response]
```

---

## 🛠️ Tool Inventory / Araç Envanteri

OmniCore includes **40+ specialized toolkits** registered in the central `ToolRegistry`:

| Category / Kategori | Toolkits / Araçlar | Description / Açıklama |
| :--- | :--- | :--- |
| **OS & Kernel** | `os_toolkit`, `advanced_os_toolkit`, `system_kernel_toolkit` | File CRUD, process management, $MFT fast search (`es_fast_search`), privilege triage (`sys_privilege_triage`), registry editing. |
| **Game Engine** | `game_updater_toolkit` | Steam VDF/ACF manifest parser, Epic Games launcher discovery, force update, and download status tracking. |
| **Voice & Audio** | `audio_toolkit`, `audio_record_toolkit`, `media_studio_toolkit` | EdgeTTS audio synthesis, SpeechRecognition microphone listener, media playback control. |
| **DevOps & Code** | `developer_toolkit`, `devops_engineering_toolkit`, `terminal_toolkit` | Cross-platform shell adapter (PowerShell/Bash), git workflows, code analysis (`dev_grep_analyzer`, `dev_glob_search`). |
| **Web & Vision** | `web_toolkit`, `advanced_web_toolkit`, `vision_toolkit`, `computer_use_toolkit` | Playwright browser automation, screenshot OCR, visual element detection, web research. |
| **Security & Safety**| `security_toolkit`, `omega_directive_toolkit`, `resilience_toolkit` | Cryptography, LOLBins audit, EDR bypass detection, policy verification. |
| **Memory & Scheduler**| `reminder_toolkit`, `scheduler_toolkit`, `insight_toolkit` | Task Scheduler reminders, cron job automation, 2-stage persistent memory categorization. |

---

## ⚡ Quick Start / Hızlı Başlangıç

### Prerequisites / Gereksinimler

- **Python**: 3.12 or higher
- **OS**: Windows 10/11, Linux, or macOS
- **Package Manager**: [uv](https://github.com/astral-sh/uv) (recommended) or `pip`

### 1. Installation / Kurulum

```bash
# Clone the repository
git clone https://github.com/MrSpy00/OmniCore.git
cd OmniCore

# Create virtual environment and install dependencies using uv
uv venv
.\.venv\Scripts\activate
uv sync
```

### 2. Configuration / Yapılandırma

Copy `.env.example` to `.env` and set your API keys:

```ini
GOOGLE_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
OMNI_LLM_MODEL=gemini-2.5-pro
```

### 3. Launching / Çalıştırma

```bash
# Interactive CLI Gateway
python -m scripts.run --cli

# Telegram Gateway
python -m scripts.run --telegram

# REST API Gateway
python -m scripts.run --rest
```

---

## 🎮 Slash Commands / Komut Satırı Kısayolları

| Command / Komut | Function / İşlev |
| :--- | :--- |
| `/plan` | Toggle Plan Mode (enforces dry-run preview for destructive operations). |
| `/doctor` | Run system diagnostics (provider status, tool count, API key availability). |
| `/memory` | Preview persistent categorized memory entries. |
| `/models` | List all available Gemini & Groq models and active configuration. |
| `/setmodel <id>` | Dynamically switch LLM model (e.g. `/setmodel gemini-2.5-pro`). |
| `/reset` | Clear current short-term conversation context. |

---

## 🧪 Testing & Verification / Test ve Doğrulama

OmniCore maintains strict code hygiene, 100% test pass rate, and zero blocking IO in async methods:

```bash
# Run full unit and integration test suite (127+ tests)
.\.venv\Scripts\pytest.exe

# Run static AST async blocking IO audit
.\.venv\Scripts\python.exe scripts/ast_async_audit.py

# Run ruff code linter
.\.venv\Scripts\ruff.exe check core tools memory models config interfaces scheduler scripts tests
```

---

## 🛡️ License & Credits / Lisans ve Teşekkürler

Licensed under the **MIT License**. Engineered for advanced agentic coding and autonomous OS operation.
