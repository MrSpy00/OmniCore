"""OmniCore GUI Launcher — Desktop entry point for windowless/GUI execution.

Launches the background FastAPI Web Dashboard, opens the default browser to
http://localhost:8080, and manages the application lifecycle.
"""

from __future__ import annotations

import asyncio
import sys
import webbrowser
from pathlib import Path

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is in sys.path
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _notify_started() -> None:
    """Send desktop notification that OmniCore has started (best-effort)."""
    if sys.platform != "win32":
        return
    # Try win10toast first
    try:
        from win10toast import ToastNotifier

        toaster = ToastNotifier()
        toaster.show_toast(
            "OmniCore AI OS",
            "Web GUI baslatildi. Tarayiciniz aciliyor: http://localhost:8080",
            duration=4,
            threaded=True,
        )
        return
    except Exception:
        pass
    # Fallback: PowerShell toast notification
    try:
        import subprocess

        ps_script = (
            "[System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            "$n.ShowBalloonTip(4000, 'OmniCore AI OS', "
            "'Web GUI baslatildi - http://localhost:8080', "
            "[System.Windows.Forms.ToolTipIcon]::Info)"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def launch_gui() -> None:
    """Launch the OmniCore Web GUI interface and open browser."""
    from scripts.run import _run

    _notify_started()

    # Schedule browser opening after server starts
    def _open():
        try:
            import time

            time.sleep(1.5)
            webbrowser.open("http://localhost:8080")
        except Exception:
            pass

    import threading

    t = threading.Thread(target=_open, daemon=True)
    t.start()

    try:
        asyncio.run(_run("web", debug=False))
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    launch_gui()
