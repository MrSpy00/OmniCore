# OmniCore v0.37.0 — Autonomous OS-Level AI Assistant Framework

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![Build Status](https://img.shields.io/badge/Tests-127%20Passed-brightgreen.svg)
![Async Hygiene](https://img.shields.io/badge/Async%20Audit-0%20Issues-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-black.svg)

**OmniCore** is a production-grade, enterprise-ready autonomous cognitive OS assistant. It bridges local system administration, kernel privilege triage, multi-drive file search, automated 2-stage persistent memory, real-time voice synthesis, Steam/Epic game engine updating, web/GUI automation, and multi-provider LLM orchestration (Gemini & Groq).

---

## 🌟 English Overview

OmniCore combines **User-Facing Capabilities** (voice loop, EdgeTTS speech, PyAudio listening, Steam & Epic launcher management, 2-stage categorized memory) with **Kernel & OS Dominance Layer** (NTFS `$MFT` / Everything `es.exe` instant file search, privilege triage via `whoami /priv` & `id`, LOLBins execution safety, and 4-tier risk governance).

### Key Features

- 🧠 **Cognitive Router & Failover**: Automatic multi-provider failover (Gemini 2.5 Pro / Flash & Groq Llama 3.3 70B) with count-based circuit breaker and semantic tool pruning.
- 💾 **2-Stage Categorized Persistent Memory**: Automatic filtering and structured JSON categorization (`identity`, `preferences`, `projects`, `relationships`, `wishes`, `notes`) with dynamic system prompt injection.
- 🎮 **Steam & Epic Game Engine Updater**: Multi-drive `libraryfolders.vdf` and `appmanifest_*.acf` parsing for Steam, Epic `Manifests/*.item` discovery, automated updates, and optional post-update auto-shutdown.
- ⚡ **Non-Blocking Async Architecture**: 100% async-native execution verified with zero blocking IO calls on main event loop threads.
- 🛡️ **4-Tier Capability Policy Governance**: Enforces `LOW`, `MEDIUM`, `HIGH`, and `CRITICAL` risk tiers with pre-action dry-run simulations, double confirmation for destructive actions, and sensitive data redaction.
- 🎙️ **Voice Loop & Spoken Announcements**: EdgeTTS synthesis, PyAudio/SpeechRecognition mic listening, mute control (`F4` hotkey / UI toggle), and pre-execution spoken announcements.
- 🔍 **Instant Disk Search ($MFT / Everything CLI)**: Instant multi-gigabyte file location discovery using `es.exe` MFT indexer with optimized fallback traversal.

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
