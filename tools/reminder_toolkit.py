"""Reminder & Scheduling Toolkit — Windows Task Scheduler integration.

Provides a ``reminder_set`` tool that uses Windows Task Scheduler (schtasks)
to create one-time reminders that survive reboots and app restarts.

Inspired by the Mark-XXXV ``reminder`` function.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from datetime import datetime

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.os_adapters import runtime_adapter

_RUNTIME = runtime_adapter()


class ReminderSet(BaseTool):
    """Create a Windows Task Scheduler one-time reminder.

    Parameters accepted (all in ``parameters`` dict):
    - ``message`` (required): Reminder text shown in the notification.
    - ``date`` (required): Date in ``YYYY-MM-DD`` format.
    - ``time`` (required): Time in ``HH:MM`` (24-hour) format.
    - ``task_name`` (optional): Custom task name (auto-generated if omitted).
    """

    name = "reminder_set"
    description = (
        "Create a timed Windows reminder using Task Scheduler. "
        "Shows a desktop notification at the specified date and time. "
        "Parameters: message (required), date (YYYY-MM-DD, required), "
        "time (HH:MM, required), task_name (optional)."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        message = str(self._first_param(params, "message", default="") or "")
        date_str = str(self._first_param(params, "date", default="") or "")
        time_str = str(self._first_param(params, "time", default="") or "")
        task_name = str(self._first_param(params, "task_name", "name", default="") or "")

        if not message:
            return self._failure("'message' parametresi zorunludur.")
        if not date_str:
            return self._failure("'date' parametresi zorunludur (YYYY-MM-DD).")
        if not time_str:
            return self._failure("'time' parametresi zorunludur (HH:MM).")

        # Validate date format
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
            return self._failure("'date' formati gecersiz. Beklenen: YYYY-MM-DD")

        # Validate time format
        if not re.fullmatch(r"\d{1,2}:\d{2}", time_str):
            return self._failure("'time' formati gecersiz. Beklenen: HH:MM")

        try:
            target_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError as exc:
            return self._failure(f"Tarih/saat ayrıştırma hatası: {exc}")

        if not _RUNTIME.is_windows:
            return self._failure(
                "Bu araç yalnızca Windows'ta çalışır. Linux/macOS için 'crontab' veya 'at' komutunu kullanın."
            )

        if not task_name:
            safe_msg = re.sub(r"[^a-zA-Z0-9]", "_", message[:20])
            task_name = f"OmniCore_Reminder_{safe_msg}_{target_dt.strftime('%Y%m%d_%H%M')}"

        # Windows schtasks date/time format: MM/DD/YYYY HH:MM
        win_date = target_dt.strftime("%m/%d/%Y")
        win_time = target_dt.strftime("%H:%M")

        # PowerShell script: create a Task Scheduler job that shows a balloon notification
        escaped_message = message.replace('"', '`"').replace("'", "`'")

        ps_action = (
            f"Add-Type -AssemblyName System.Windows.Forms; "
            f"$notify = New-Object System.Windows.Forms.NotifyIcon; "
            f"$notify.Icon = [System.Drawing.SystemIcons]::Information; "
            f"$notify.Visible = $true; "
            f"$notify.ShowBalloonTip(10000, 'OmniCore Hatırlatıcı', '{escaped_message}', "
            f"[System.Windows.Forms.ToolTipIcon]::Info)"
        )

        cmd = [
            "schtasks",
            "/Create",
            "/TN",
            task_name,
            "/TR",
            f'powershell -WindowStyle Hidden -Command "{ps_action}"',
            "/SC",
            "ONCE",
            "/SD",
            win_date,
            "/ST",
            win_time,
            "/F",  # force overwrite if exists
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return self._failure(f"schtasks komutu başarısız: {exc}")

        if result.returncode == 0:
            return self._success(
                f"Hatırlatıcı oluşturuldu: '{message}' — {date_str} {win_time}",
                data={
                    "task_name": task_name,
                    "scheduled_for": f"{date_str}T{win_time}",
                    "message": message,
                },
            )

        stderr = (result.stderr or "").strip()
        return self._failure(f"schtasks hatası (kod {result.returncode}): {stderr or result.stdout}")


class ReminderList(BaseTool):
    """List all OmniCore reminders in Windows Task Scheduler."""

    name = "reminder_list"
    description = "List all OmniCore reminders currently scheduled in Windows Task Scheduler."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta çalışır.")

        cmd = ["schtasks", "/Query", "/FO", "CSV", "/NH"]
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            return self._failure(f"schtasks sorgu hatası: {exc}")

        if result.returncode != 0:
            return self._failure(f"schtasks hatası: {result.stderr}")

        lines = [line for line in result.stdout.splitlines() if "OmniCore_Reminder" in line]
        tasks = []
        for line in lines:
            parts = line.strip().strip('"').split('","')
            if parts:
                tasks.append({"task": parts[0], "next_run": parts[1] if len(parts) > 1 else "?"})

        return self._success(
            f"{len(tasks)} OmniCore hatırlatıcısı bulundu.",
            data={"reminders": tasks, "count": len(tasks)},
        )


class ReminderDelete(BaseTool):
    """Delete an OmniCore reminder from Windows Task Scheduler."""

    name = "reminder_delete"
    description = "Delete an OmniCore reminder from Windows Task Scheduler. Parameters: task_name (required)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not _RUNTIME.is_windows:
            return self._failure("Bu araç yalnızca Windows'ta çalışır.")

        params = self._params(tool_input)
        task_name = str(self._first_param(params, "task_name", "name", default="") or "")
        if not task_name:
            return self._failure("'task_name' parametresi zorunludur.")

        cmd = ["schtasks", "/Delete", "/TN", task_name, "/F"]
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as exc:
            return self._failure(f"schtasks silme hatası: {exc}")

        if result.returncode == 0:
            return self._success(
                f"Hatırlatıcı silindi: {task_name}",
                data={"task_name": task_name},
            )
        return self._failure(f"Silme hatası: {result.stderr or result.stdout}")
