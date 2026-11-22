# Contributing to OmniCore

Thanks for contributing to OmniCore.

## Local Setup

```bash
uv venv
uv sync --dev
```

## Checks Before Opening a PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest --tb=short -q --cov --cov-fail-under=70
```

- Maintain >=70% test coverage across `core/` and `memory/`.
- Do not commit `.env`, API keys, `.db`, or generated `logs/` / `data/` directories.
- Keep commits small and focused (`feat:`, `fix:`, `docs:`, `test:`).
