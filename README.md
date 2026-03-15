# OmniCore

Autonomous OS-level AI assistant with modular architecture. Executes complex multi-step workflows, browses the web, manages files (sandboxed), and interacts via Telegram, CLI, or REST API.

Provider-agnostic LLM support (Gemini or Groq) via LangChain.

## Architecture

```
User Message
    |
    v
Gateway (Telegram / CLI / REST API)
    |
    v
Cognitive Router  <-->  Memory (Short-term + Long-term ChromaDB + SQLite state)
    |
    v
Planner  -->  TaskPlan [Step 1, Step 2, ...]
    |
    v
Guardian (HITL approval for destructive ops)
    |
    v
RecoveryEngine (exponential backoff retries)
    |
    v
Tool Execution (OS / Terminal / Web / API toolkits)
    |
    v
Response summarized by LLM --> Gateway --> User
```

### Modules

| Module | Path | Purpose |
|--------|------|---------|
| **Cognitive Router** | `core/router.py` | Central LLM brain -- intent classification, CoT decomposition, tool routing |
| **Memory** | `memory/` | Short-term sliding window, ChromaDB long-term vectors, SQLite state tracking |
| **Tools** | `tools/` | Registry + 4 toolkits: OS (6 tools), Terminal (1), Web (3 Playwright), API (3) |
| **Gateways** | `interfaces/` | Telegram bot (primary), CLI REPL, FastAPI REST |
| **Scheduler** | `scheduler/` | APScheduler daemon with builtin + user-defined cron jobs |

### Safety

- All file operations sandboxed to `SANDBOX_ROOT`
- Destructive actions (delete, overwrite, shell exec) require human-in-the-loop approval
- HITL timeout: configurable (default 5 min), aborts on timeout
- All approval decisions logged to SQLite `audit_log` table
- Error recovery with exponential backoff (max 2 retries per step)

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A Google Gemini API key or Groq API key
- A Telegram Bot Token (for Telegram gateway)

### Install

```bash
# Clone and enter the project
git clone <repo-url>
cd OmniCore

# Install all dependencies
uv sync

# Install Playwright browser
uv run playwright install chromium

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY and TELEGRAM_BOT_TOKEN
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_PROVIDER` | No | `gemini` | LLM provider (`gemini` or `groq`) |
| `GOOGLE_API_KEY` | When provider=gemini | -- | Google Gemini API key |
| `GROQ_API_KEY` | When provider=groq | -- | Groq API key |
| `GROQ_LLM_MODEL` | No | `llama-3.3-70b-versatile` | Groq model name |
| `TELEGRAM_BOT_TOKEN` | Telegram mode | -- | Telegram Bot API token |
| `TELEGRAM_ALLOWED_USERS` | No | (all) | Comma-separated Telegram user IDs |
| `OMNI_LLM_MODEL` | No | `gemini-1.5-pro` | Gemini model name |
| `HITL_TIMEOUT_MINUTES` | No | `5` | Approval timeout in minutes |
| `SANDBOX_ROOT` | No | `./workspace` | Sandboxed directory for file ops |
| `CHROMA_PERSIST_DIR` | No | `./data/chromadb` | ChromaDB storage path |
| `SQLITE_DB_PATH` | No | `./data/omnicore.db` | SQLite database path |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `SCHEDULER_ENABLED` | No | `true` | Enable/disable background scheduler |

## Usage

### Telegram Bot (primary)

```bash
uv run python scripts/run.py --mode telegram
```

Bot commands:
- `/start` -- Welcome message
- `/status` -- Show system status (memory, tasks, tools)
- `/clear` -- Clear conversation history

Destructive operations present an inline keyboard with Approve/Deny buttons.

### CLI REPL

```bash
uv run python scripts/run.py --mode cli
```

Interactive prompt. Destructive actions prompt for `y/n` confirmation in the terminal.

### REST API

```bash
uv run python scripts/run.py --mode api
```

Endpoints:
- `GET /health` -- Health check
- `POST /chat` -- `{"user_id": "...", "text": "..."}` -> `{"response": "..."}`

## Tools

### OS Toolkit (sandboxed)
| Tool | Destructive | Description |
|------|:-----------:|-------------|
| `os_read_file` | No | Read file contents |
| `os_write_file` | Yes | Write/overwrite a file |
| `os_list_dir` | No | List directory contents |
| `os_move_file` | Yes | Move/rename a file |
| `os_delete_file` | Yes | Delete a file |
| `os_system_info` | No | CPU, memory, disk, platform info |

### Terminal Toolkit
| Tool | Destructive | Description |
|------|:-----------:|-------------|
| `terminal_execute` | Yes | Execute shell command (60s timeout) |

### Web Toolkit (Playwright)
| Tool | Destructive | Description |
|------|:-----------:|-------------|
| `web_navigate` | No | Navigate to URL and extract text |
| `web_search` | No | Search the web via DuckDuckGo |
| `web_screenshot` | No | Take a screenshot of a webpage |

### API Toolkit
| Tool | Destructive | Description |
|------|:-----------:|-------------|
| `api_http_request` | No | Make arbitrary HTTP requests |
| `api_weather` | No | Get weather for a location |
| `api_datetime` | No | Get current date/time info |

## Testing

```bash
uv run pytest -v
```

23 tests covering: router intent classification, planner, guardian HITL (approve/deny/timeout), short-term memory, state tracker CRUD, tool registry, OS toolkit, API toolkit, and scheduler jobs.

## Project Structure

```
OmniCore/
├── config/          # Pydantic Settings, structlog setup
├── models/          # Data models (messages, tasks, tools)
├── memory/          # Short-term, long-term (ChromaDB), state (SQLite)
├── tools/           # BaseTool ABC, registry, 4 toolkits
├── core/            # Router, planner, guardian, recovery engine
├── interfaces/      # Telegram bot, CLI REPL, FastAPI REST
├── scheduler/       # APScheduler daemon, builtin jobs
├── db/              # Schema DDL, migrations placeholder
├── scripts/         # Entrypoints (run.py, setup_db.py)
├── tests/           # pytest suite (23 tests)
├── pyproject.toml   # Dependencies and project config
└── .env.example     # Environment variable template
```

## Tech Stack

Python 3.12 | LangChain | Google Gemini | ChromaDB | SQLite (aiosqlite) | Playwright | APScheduler | structlog | Pydantic v2 | httpx | FastAPI | python-telegram-bot v21+
# OmniCore
"# OmniCore" 
