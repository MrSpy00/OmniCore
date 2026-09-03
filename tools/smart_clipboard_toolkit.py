"""Smart Clipboard Intelligence Toolkit — Inspect, classify, and analyze clipboard content."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool

try:
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None  # type: ignore[assignment]


def _detect_content_type(text: str) -> dict[str, Any]:
    """Detect whether text is a traceback, JSON, SQL, URL, or code snippet."""
    clean = text.strip()
    if not clean:
        return {"type": "empty", "category": "empty"}

    # 1. Python traceback
    if "Traceback (most recent call last):" in clean or re.search(r"File \".*\", line \d+", clean):
        lines = [line.strip() for line in clean.splitlines() if line.strip()]
        last_line = lines[-1] if lines else ""
        return {
            "type": "python_traceback",
            "category": "error",
            "error_summary": last_line,
        }

    # 2. JavaScript / Node.js error
    if re.search(r"^\w*Error:.*(?:\n\s+at\s+.*)+", clean, flags=re.MULTILINE):
        return {
            "type": "javascript_traceback",
            "category": "error",
            "error_summary": clean.splitlines()[0],
        }

    # 3. Valid JSON
    if (clean.startswith("{") and clean.endswith("}")) or (clean.startswith("[") and clean.endswith("]")):
        try:
            parsed = json.loads(clean)
            return {
                "type": "json",
                "category": "data",
                "json_keys": list(parsed.keys()) if isinstance(parsed, dict) else len(parsed),
            }
        except Exception:
            pass

    # 4. SQL query
    sql_keywords = r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE)\b"
    if re.search(sql_keywords, clean, flags=re.IGNORECASE):
        return {
            "type": "sql_query",
            "category": "database",
        }

    # 5. URL
    if re.match(r"^https?://[^\s]+$", clean):
        return {
            "type": "url",
            "category": "web",
            "url": clean,
        }

    # 6. Shell command
    shell_prefixes = ("git ", "npm ", "uv ", "pip ", "docker ", "kubectl ", "cargo ", "python ", "curl ")
    if any(clean.startswith(p) for p in shell_prefixes):
        return {
            "type": "shell_command",
            "category": "terminal",
        }

    return {
        "type": "plain_text",
        "category": "text",
    }


class SmartClipboardInspect(BaseTool):
    """Inspect and classify the current contents of the system clipboard."""

    name = "smart_clipboard_inspect"
    description = (
        "Inspect the current system clipboard content and detect if it is an error traceback, "
        "code snippet, JSON, SQL query, or URL."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not pyperclip:
            return self._failure("pyperclip is not available on this system.")

        def _worker() -> dict[str, Any]:
            content = pyperclip.paste()
            detection = _detect_content_type(content)
            return {
                "length": len(content),
                "preview": content[:200] + ("..." if len(content) > 200 else ""),
                "detection": detection,
            }

        data = await asyncio.to_thread(_worker)
        dt = data["detection"]
        summary = f"Pano İçeriği: Tür={dt['type']} ({dt['category']}), Boyut={data['length']} karakter."
        if dt.get("error_summary"):
            summary += f"\nTespit Edilen Hata: {dt['error_summary']}"
        return self._success(summary, data=data)


class SmartClipboardAnalyzeTraceback(BaseTool):
    """Analyze an error traceback currently stored in the clipboard and provide a diagnosis."""

    name = "smart_clipboard_analyze_traceback"
    description = (
        "Analyze a traceback or error message stored in the clipboard, extract the exception type, "
        "failing file, line number, and suggest fixes."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not pyperclip:
            return self._failure("pyperclip is not available.")

        def _worker() -> dict[str, Any]:
            content = pyperclip.paste()
            detection = _detect_content_type(content)

            if detection["category"] != "error":
                return {
                    "is_error": False,
                    "content_type": detection["type"],
                    "message": "Panoda bir hata izi (traceback) tespit edilemedi.",
                }

            # Parse failing file and line
            files_lines = re.findall(r'File "([^"]+)", line (\d+)(?:, in (\w+))?', content)
            exc_match = re.search(r"^(\w+(?:Error|Exception|Warning|Fault)): (.*)$", content, flags=re.MULTILINE)

            exc_type = exc_match.group(1) if exc_match else "UnknownError"
            exc_msg = exc_match.group(2) if exc_match else detection.get("error_summary", "")

            diagnosis = {
                "is_error": True,
                "exception_type": exc_type,
                "exception_message": exc_msg,
                "call_stack": [{"file": f, "line": int(line_num), "function": fn} for f, line_num, fn in files_lines],
            }
            return diagnosis

        res = await asyncio.to_thread(_worker)
        if not res.get("is_error"):
            return self._success(res["message"], data=res)

        failing = res["call_stack"][-1] if res.get("call_stack") else None
        loc_str = f" ({failing['file']}:{failing['line']})" if failing else ""
        msg = (
            f"❌ Hata Analizi: {res['exception_type']}: {res['exception_message']}{loc_str}\n"
            f"Toplam Stack Derinliği: {len(res.get('call_stack', []))} çağrı."
        )
        return self._success(msg, data=res)


class SmartClipboardGetHistory(BaseTool):
    """Pano değişim geçmişini içerik türü algılama ile birlikte döndürür."""

    name = "smart_clipboard_get_history"
    description = (
        "Get recent clipboard change history with content type detection "
        "(traceback, code, JSON, URL, etc). Shows what was copied recently."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        limit = int(self._first_param(params, "limit") or 10)

        try:
            from tools.clipboard_watcher import get_clipboard_watcher

            watcher = get_clipboard_watcher()
            history = watcher.get_history(limit=limit)

            if not history:
                return self._success("Panoda henüz bir değişiklik algılanmadı.", data={"history": []})

            entries = []
            for entry in history:
                entries.append(
                    {
                        "timestamp": entry.get("timestamp"),
                        "preview": entry.get("content_preview", "")[:100],
                        "type": entry.get("content_type", {}).get("category", "unknown"),
                        "length": entry.get("content_length", 0),
                    }
                )

            summary = f"Son {len(entries)} pano değişikliği:"
            for i, e in enumerate(entries, 1):
                summary += f"\n{i}. [{e['type']}] {e['preview'][:50]}..."

            return self._success(summary, data={"history": entries})
        except Exception as exc:
            return self._failure(f"Pano geçmişi alınamadı: {exc}")


def show_windows_toast(title: str, message: str) -> None:
    """Display a native Windows toast notification using PowerShell."""
    import subprocess

    clean_title = title.replace('"', '`"')
    clean_msg = message.replace('"', '`"')
    ps = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $toastXml = [Windows.Data.Xml.Dom.XmlDocument]::new()
    $toastXml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>{clean_title}</text><text>{clean_msg}</text></binding></visual></toast>")
    $toast = [Windows.UI.Notifications.ToastNotification]::new($toastXml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("OmniCore").Show($toast)
    """
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=5)
    except Exception:
        pass


class ClipboardAnalyze(BaseTool):
    """Analyze current clipboard content and suggest or execute contextual workflows."""

    name = "clipboard_analyze"
    description = (
        "Inspect and analyze current clipboard content, diagnose errors, format JSON/SQL, "
        "and optionally show a Windows toast notification. Parameters: notify (bool)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        if not pyperclip:
            return self._failure("pyperclip is not available.")

        params = self._params(tool_input)
        notify = bool(params.get("notify", False))

        content = pyperclip.paste()
        detection = _detect_content_type(content)
        cat = detection.get("category", "text")
        typ = detection.get("type", "plain_text")

        suggestion = "İçerik normal metin olarak algılandı."
        action = "none"

        if cat == "error":
            suggestion = f"Hata algılandı: {detection.get('error_summary', 'Traceback')}. Çözüm önerisi üretilebilir."
            action = "analyze_error"
        elif typ == "json":
            suggestion = "JSON verisi algılandı. Doğrulama ve formatlama yapılabilir."
            action = "format_json"
        elif typ == "sql_query":
            suggestion = "SQL sorgusu algılandı. Sorgu analizi yapılabilir."
            action = "analyze_sql"
        elif typ == "url":
            suggestion = f"Web bağlantısı algılandı: {detection.get('url')}. İçerik indirilebilir."
            action = "fetch_url"

        if notify:
            await asyncio.to_thread(show_windows_toast, f"OmniCore Pano: {cat.upper()}", suggestion)

        return self._success(
            f"Pano Analizi Tamamlandı: {suggestion}",
            data={
                "category": cat,
                "type": typ,
                "suggestion": suggestion,
                "recommended_action": action,
                "length": len(content),
            },
        )
