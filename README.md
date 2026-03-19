# OmniCore

OmniCore is a host-level AGI-style operations agent with dynamic tool loading, multi-step planning, memory, and guarded execution. It is designed to run real actions across your machine and network with minimal abstraction between intent and execution.

## Omni-Core Reality

- Real host execution: file, process, network, and browser operations run on the real OS.
- Multi-drive and cross-root pathing: Windows (`C:\`, `D:\`, `E:\`), Linux/macOS (`/`, `/var`, `/etc`) are treated as first-class targets.
- Dynamic path intelligence: Windows special folders are resolved from Registry shell folders (OneDrive-safe Desktop/Documents/Downloads).
- Tool ecosystem at scale: 100+ tools discovered dynamically from `tools/` at runtime.
- Hydra LLM fallback chain: multi-key Groq rotation + multi-model fallback sequence.

## Core Capabilities

- Cognitive routing from user intent to actionable tools.
- Multi-step planning with state tracking.
- Human-in-the-loop guardrails for destructive actions.
- Retry and anti-loop recovery behavior.
- Local memory stack:
  - short-term conversational memory,
  - vector memory (ChromaDB),
  - SQLite task/audit state.

## Architecture

```text
User Input
  -> Gateway (Telegram / CLI / REST)
  -> Cognitive Router (intent + tool selection)
  -> Planner (task graph / step list)
  -> Guardian (approval for destructive ops)
  -> Recovery Engine (retry / anti-loop)
  -> Tool Execution Layer (dynamic registry)
  -> Response Synthesis
```

## Tooling System

OmniCore loads tools dynamically from `tools/` and registers each concrete `BaseTool` implementation.

- Auto-discovery module: `tools/registry.py`
- Contract base: `tools/base.py`
- Tool metadata surfaced to router prompt at runtime

Representative domains include:

- OS and filesystem operations
- terminal and process control
- deep search and network infrastructure tasks
- browser automation (Playwright)
- API and integrations
- media, vision, and automation utilities

## Multi-Drive and Cross-Platform Pathing

Path resolution lives in `tools/base.py` (`resolve_user_path`) and follows these rules:

1. Any absolute path is honored as provided.
   - Windows examples: `D:\Games`, `E:\Backups`, `C:\Windows\System32`
   - POSIX examples: `/`, `/var/log`, `/etc`
2. Relative paths resolve against host home directory.
3. Windows aliases (`Desktop`, `Documents`, `Downloads`) resolve using Registry `User Shell Folders` values.

This design removes single-drive assumptions and supports true cross-volume operation.

## Hydra 3-Tier LLM Fallback

The Groq chain supports both key and model fallback:

- Key rotation pool: `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`
- Model chain:
  - `GROQ_PRIMARY_MODEL`
  - `GROQ_FALLBACK_MODEL_1`
  - `GROQ_FALLBACK_MODEL_2`

Legacy compatibility remains for:

- `GROQ_API_KEY`
- `GROQ_LLM_MODEL`
- `GROQ_FALLBACK_MODELS`

## Quick Start

### Prerequisites

- Python 3.12+
- `uv`
- Optional: Playwright Chromium (`uv run playwright install chromium`)

### Install

```bash
git clone <repo-url>
cd OmniCore
uv sync
uv run playwright install chromium
cp .env.example .env
```

### Run Modes

```bash
# CLI
uv run python scripts/run.py --mode cli

# Telegram
uv run python scripts/run.py --mode telegram

# REST API
uv run python scripts/run.py --mode api
```

## Environment Variables

See `.env.example` for the full template.

Core fields include:

- `LLM_PROVIDER`
- `GOOGLE_API_KEY`
- `OMNI_LLM_MODEL`
- `GROQ_API_KEY`, `GROQ_API_KEY_1..3`
- `GROQ_PRIMARY_MODEL`, `GROQ_FALLBACK_MODEL_1`, `GROQ_FALLBACK_MODEL_2`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`
- `HITL_TIMEOUT_MINUTES`
- `CHROMA_PERSIST_DIR`, `SQLITE_DB_PATH`
- `SCHEDULER_ENABLED`, `LOG_LEVEL`

## Testing

```bash
uv run pytest -v
```

The suite validates router behavior, memory/state, tool registration, toolkit execution paths, and regression expectations for platform/path features.

## Repository Layout

```text
config/       settings + logging
core/         router, planner, guardian, recovery
interfaces/   Telegram, CLI, REST
memory/       short-term + vector + SQLite state
models/       shared data contracts
scheduler/    APScheduler jobs
tools/        dynamic tool modules (100+)
tests/        pytest suite
scripts/      startup and utility entrypoints
```

## Safety Notes

- Destructive tools are flagged and routed through approval policies.
- Tool outputs preserve raw execution data (`raw_output`, stderr/stdout, return codes) where applicable.
- Blocking operations are executed via async-safe wrappers (`asyncio.to_thread`) across toolkit boundaries.
