"""Hardware Telemetry Toolkit — Hardware and thermal sensors inspector."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import psutil

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class HardwareInspectTelemetry(BaseTool):
    """Inspect CPU, GPU, memory, thermal sensors, and disk I/O metrics."""

    name = "hardware_inspect_telemetry"
    description = "Inspect system CPU frequencies, GPU VRAM, thermal sensors, and disk I/O."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        telemetry = await asyncio.to_thread(_collect_hardware_telemetry)
        return self._success("Hardware telemetry collected successfully.", data=telemetry)


def _collect_hardware_telemetry() -> dict[str, Any]:
    cpu_freq = psutil.cpu_freq()
    battery = psutil.sensors_battery()
    disk_io = psutil.disk_io_counters()

    gpu_info = _get_nvidia_gpu_info()

    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_freq_mhz": cpu_freq.current if cpu_freq else None,
        "ram_percent": psutil.virtual_memory().percent,
        "battery_percent": battery.percent if battery else None,
        "battery_plugged": battery.power_plugged if battery else None,
        "disk_read_bytes": disk_io.read_bytes if disk_io else 0,
        "disk_write_bytes": disk_io.write_bytes if disk_io else 0,
        "gpu": gpu_info,
    }


def _get_nvidia_gpu_info() -> dict[str, Any]:
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,temperature.gpu,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 5:
                return {
                    "name": parts[0],
                    "vram_total_mb": parts[1],
                    "vram_used_mb": parts[2],
                    "temp_c": parts[3],
                    "utilization_percent": parts[4],
                }
    except Exception:
        pass
    return {"available": False}
