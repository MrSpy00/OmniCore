# ADR-0001: Circuit Breaker, Semantic Routing, and OS Adapter Factory

## Status
Accepted

## Context
OmniCore routes user requests to external LLM providers and executes host-level commands.
This creates two architectural risks:
1. External provider instability (e.g., quota/rate-limit failures).
2. Platform branching complexity in shell execution.

Additional constraints include strict input/output validation and bounded execution context.

## Decision
1. Add a count-based Circuit Breaker in `core/router.py`.
- Threshold: 3 retryable failures.
- Cooldown: 30 seconds.
- When open, router returns deterministic local fallback response immediately.

2. Add semantic provider routing in `core/router.py`.
- Use lightweight token estimation `len(text) // 4`.
- Route larger prompts to Gemini profile automatically.

3. Add `asyncio.Semaphore` around LLM invocation.
- Limit concurrent external calls to prevent burst failures.

4. Introduce Abstract Factory for OS shell bootstrap.
- New `tools/os_adapters.py` defines `BaseShellAdapter`, `WindowsShellAdapter`, `PosixShellAdapter`, and lazy `ShellAdapterFactory`.
- `tools/terminal_toolkit.py` now delegates shell argv construction to the factory.

5. Enforce stricter output schema.
- `models/tools.py` now uses strict `ToolOutput` config (`extra=forbid`, assignment validation, validated `tool_name`).

6. Add AST async audit script.
- New `scripts/ast_async_audit.py` reports blocking IO inside async functions and possible zombie coroutine patterns.

## Consequences
### Positive
- Faster graceful degradation under external quota failures.
- Reduced platform-specific conditional sprawl.
- Improved runtime safety via bounded concurrency and stronger schema contracts.
- Auditable static analysis path for async hygiene.

### Trade-offs
- Circuit breaker introduces temporary fail-fast window.
- Semantic routing uses heuristic token estimation, not exact tokenizer counts.

## Follow-up
1. Extend OS adapter abstraction to other OS-facing toolkits.
2. Add per-provider breaker metrics and structured telemetry.
3. Add CI job to run `scripts/ast_async_audit.py` and fail on new high-severity findings.
