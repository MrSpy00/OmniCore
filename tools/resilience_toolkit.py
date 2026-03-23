"""Enterprise resilience toolkit.

Contains lightweight operational diagnostics tools:
- sys_health_monitor
- net_latency_profiler
- vision_self_healing_ui
"""

from __future__ import annotations

import asyncio
import gc
import statistics
import time
import tracemalloc
from typing import Any

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

_NET_SEMAPHORE = asyncio.Semaphore(8)


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class SysHealthMonitor(BaseTool):
    """Heuristic process health check.

    Complexity: O(1) for metrics retrieval in this implementation.
    """

    name = "sys_health_monitor"
    description = "Collect GC and memory health indicators for leak suspicion analysis."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            sample_seconds = _coerce_float(params.get("sample_seconds"), 0.5)
            sample_seconds = min(max(sample_seconds, 0.1), 5.0)

            tracemalloc.start()
            snap1 = tracemalloc.take_snapshot()
            await asyncio.sleep(sample_seconds)
            gc.collect()
            snap2 = tracemalloc.take_snapshot()
            top_stats = snap2.compare_to(snap1, "lineno")[:5]

            growth_bytes = sum(max(0, stat.size_diff) for stat in top_stats)
            suspicion = "low"
            if growth_bytes > 5_000_000:
                suspicion = "high"
            elif growth_bytes > 1_000_000:
                suspicion = "medium"

            return self._success(
                "System health sample collected",
                data={
                    "sample_seconds": sample_seconds,
                    "gc_counts": list(gc.get_count()),
                    "growth_bytes": growth_bytes,
                    "suspicion": suspicion,
                    "top_growth": [
                        {
                            "trace": str(stat.traceback).splitlines()[-1] if stat.traceback else "",
                            "size_diff": stat.size_diff,
                            "count_diff": stat.count_diff,
                        }
                        for stat in top_stats
                    ],
                },
            )
        except Exception as exc:
            return self._failure(f"sys_health_monitor failed: {exc}")


class NetLatencyProfiler(BaseTool):
    """Profile connection latency asynchronously.

    Complexity: O(n) where n is `samples`.
    """

    name = "net_latency_profiler"
    description = "Measure async TCP connect latency distribution for a host:port."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        host = str(self._first_param(params, "host", default="1.1.1.1"))
        port = int(self._first_param(params, "port", default=443))
        samples = int(self._first_param(params, "samples", default=5))
        timeout = _coerce_float(params.get("timeout"), 2.0)
        samples = min(max(samples, 1), 20)
        timeout = min(max(timeout, 0.2), 10.0)

        results_ms: list[float] = []
        errors: list[str] = []

        for _ in range(samples):
            async with _NET_SEMAPHORE:
                started = time.perf_counter()
                writer = None
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port),
                        timeout=timeout,
                    )
                    _ = reader
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    results_ms.append(elapsed_ms)
                except Exception as exc:
                    errors.append(str(exc))
                finally:
                    if writer is not None:
                        writer.close()
                        await writer.wait_closed()

        if not results_ms:
            return self._failure(
                f"No successful samples. host={host} port={port} errors={errors[:3]}"
            )

        return self._success(
            "Latency profile computed",
            data={
                "host": host,
                "port": port,
                "samples": samples,
                "success_count": len(results_ms),
                "error_count": len(errors),
                "min_ms": min(results_ms),
                "max_ms": max(results_ms),
                "avg_ms": statistics.fmean(results_ms),
                "p95_ms": _percentile(results_ms, 95.0),
                "errors": errors[:5],
            },
        )


class VisionSelfHealingUI(BaseTool):
    """Generate self-healing coordinate candidates after click failure.

    Complexity: O(k) where k is candidate count.
    """

    name = "vision_self_healing_ui"
    description = "Recalculate robust candidate coordinates after GUI click failure."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            x = int(self._first_param(params, "x", default=0))
            y = int(self._first_param(params, "y", default=0))
            jitter = int(self._first_param(params, "jitter", default=24))
            retries = int(self._first_param(params, "retries", default=5))

            retries = min(max(retries, 1), 16)
            jitter = min(max(jitter, 4), 120)

            strategy = str(self._first_param(params, "strategy", default="spiral")).lower()
            match strategy:
                case "grid":
                    candidates = _grid_candidates(x, y, jitter, retries)
                case _:
                    candidates = _spiral_candidates(x, y, jitter, retries)

            return self._success(
                "Self-healing candidates generated",
                data={
                    "base": {"x": x, "y": y},
                    "strategy": strategy,
                    "candidates": candidates,
                    "next_action": "Try candidates sequentially and re-run OCR after each click.",
                },
            )
        except Exception as exc:
            return self._failure(f"vision_self_healing_ui failed: {exc}")


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int((len(ordered) - 1) * (q / 100.0))
    return ordered[idx]


def _spiral_candidates(x: int, y: int, jitter: int, retries: int) -> list[dict[str, int]]:
    offsets = [(0, 0), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    candidates: list[dict[str, int]] = []
    ring = 0
    while len(candidates) < retries:
        for ox, oy in offsets:
            candidates.append(
                {
                    "x": x + ox * jitter * (ring + 1),
                    "y": y + oy * jitter * (ring + 1),
                }
            )
            if len(candidates) >= retries:
                break
        ring += 1
    return candidates


def _grid_candidates(x: int, y: int, jitter: int, retries: int) -> list[dict[str, int]]:
    candidates: list[dict[str, int]] = []
    radius = 0
    while len(candidates) < retries:
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                candidates.append({"x": x + dx * jitter, "y": y + dy * jitter})
                if len(candidates) >= retries:
                    return candidates
        radius += 1
    return candidates
