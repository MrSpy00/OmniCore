"""Cyberpunk Terminal Telemetry HUD — Real-time visual panel for CLI mode."""

from __future__ import annotations

import psutil


def generate_cyberpunk_hud_panel(
    router_provider: str = "gemini",
    memory_nodes: int = 0,
    active_daemons: int = 0,
    tools_count: int = 40,
) -> str:
    """Generate a stylized ASCII cyberpunk telemetry HUD panel string."""
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent

    cpu_bar = _make_progress_bar(cpu)
    ram_bar = _make_progress_bar(ram)

    lines = [
        " ┌────────────────────────────────────────────────────────┐",
        " │ ⚡ OMNICORE CYBERPUNK TELEMETRY HUD v0.39.0             │",
        " ├────────────────────────────────────────────────────────┤",
        f" │ 🤖 ROUTER: [{router_provider.upper():<8}]  🛠️ TOOLS: {tools_count:<3}           │",
        f" │ 🕸️ GRAPH: [{memory_nodes} nodes]  🔄 DAEMONS: {active_daemons:<3}         │",
        " ├────────────────────────────────────────────────────────┤",
        f" │ 💻 CPU: [{cpu_bar}] {cpu:>5.1f}%                   │",
        f" │ 🧠 RAM: [{ram_bar}] {ram:>5.1f}%                   │",
        " └────────────────────────────────────────────────────────┘",
    ]
    return "\n".join(lines)


def _make_progress_bar(percent: float, width: int = 20) -> str:
    filled = int((percent / 100.0) * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)
