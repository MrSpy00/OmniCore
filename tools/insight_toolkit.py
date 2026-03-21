"""Insight Toolkit - lightweight analysis and validation helpers."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


class DataHashText(BaseTool):
    name = "data_hash_text"
    description = "Generate deterministic hash for text using md5/sha1/sha256/sha512."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            text = str(self._first_param(params, "text", "content", "value", default=""))
            algorithm = str(
                self._first_param(params, "algorithm", "algo", default="sha256")
            ).lower()
            if algorithm not in {"md5", "sha1", "sha256", "sha512"}:
                return self._failure("Unsupported algorithm. Use md5, sha1, sha256, or sha512.")
            digest = hashlib.new(algorithm, text.encode("utf-8")).hexdigest()
            return self._success(
                f"Generated {algorithm} hash",
                data={"algorithm": algorithm, "hash": digest, "length": len(text)},
            )
        except Exception as exc:
            return self._failure(str(exc))


class TextProfileBasic(BaseTool):
    name = "text_profile_basic"
    description = "Compute basic text profile: lines, words, chars, and top tokens."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            text = str(self._first_param(params, "text", "content", "value", default=""))
            stripped = text.strip()
            words = stripped.split() if stripped else []
            lines = text.splitlines() if text else []
            tokens = [w.strip(".,!?;:\"'()[]{}") for w in words]
            tokens = [t.lower() for t in tokens if t]
            top_tokens = Counter(tokens).most_common(int(params.get("top_n", 10) or 10))
            return self._success(
                "Text profile calculated",
                data={
                    "chars": len(text),
                    "words": len(words),
                    "lines": len(lines),
                    "top_tokens": [{"token": t, "count": c} for t, c in top_tokens],
                },
            )
        except Exception as exc:
            return self._failure(str(exc))


class DataValidateJson(BaseTool):
    name = "data_validate_json"
    description = "Validate JSON text and optionally assert required top-level keys."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            value = self._first_param(params, "json", "text", "content", "value")
            if value is None:
                return self._failure("json/text/content is required")
            parsed = json.loads(str(value))
            required = params.get("required_keys") or []
            missing: list[str] = []
            if isinstance(required, list) and isinstance(parsed, dict):
                missing = [str(k) for k in required if str(k) not in parsed]
            is_valid = not missing
            message = "JSON is valid" if is_valid else "JSON valid but missing required keys"
            return self._success(
                message,
                data={
                    "valid": is_valid,
                    "type": type(parsed).__name__,
                    "missing_required_keys": missing,
                },
            )
        except Exception as exc:
            return self._failure(f"Invalid JSON: {exc}")


class DataCsvProfile(BaseTool):
    name = "data_csv_profile"
    description = "Profile CSV file: row count, columns, null-like counts, and preview."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "path", "file_path", "value")
            if not path_value:
                return self._failure("path is required")
            path, _ = resolve_user_path(str(path_value))
            if not path.exists() or not path.is_file():
                return self._failure(f"CSV file not found: {path}")

            delimiter = str(params.get("delimiter", ","))
            max_rows = int(params.get("max_rows", 2000) or 2000)
            preview_rows = int(params.get("preview_rows", 5) or 5)

            profile = await asyncio.to_thread(
                _profile_csv_file,
                path,
                delimiter,
                max_rows,
                preview_rows,
            )
            return self._success("CSV profile generated", data=profile)
        except Exception as exc:
            return self._failure(str(exc))


class OsPathInspect(BaseTool):
    name = "os_path_inspect"
    description = "Inspect host path metadata (type, size, and timestamps)."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        try:
            params = self._params(tool_input)
            path_value = self._first_param(params, "path", "file_path", "value")
            if not path_value:
                return self._failure("path is required")
            path, _ = resolve_user_path(str(path_value))
            exists = path.exists()
            data: dict[str, Any] = {
                "path": str(path),
                "exists": exists,
            }
            if not exists:
                return self._success("Path inspected", data=data)

            stat = await asyncio.to_thread(path.stat)
            data.update(
                {
                    "type": "directory" if path.is_dir() else "file",
                    "size_bytes": int(stat.st_size),
                    "modified_ts": float(stat.st_mtime),
                    "created_ts": float(stat.st_ctime),
                }
            )
            return self._success("Path inspected", data=data)
        except Exception as exc:
            return self._failure(str(exc))


def _profile_csv_file(
    path: Path,
    delimiter: str,
    max_rows: int,
    preview_rows: int,
) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    rows: list[dict[str, Any]] = []
    null_like = {"", "na", "n/a", "null", "none", "nan"}

    columns = list(reader.fieldnames or [])
    null_counts = {col: 0 for col in columns}
    row_count = 0

    for row in reader:
        row_count += 1
        if row_count <= preview_rows:
            rows.append(dict(row))
        for col in columns:
            val = str((row.get(col) if row else "") or "").strip().lower()
            if val in null_like:
                null_counts[col] += 1
        if row_count >= max_rows:
            break

    return {
        "path": str(path),
        "row_count": row_count,
        "columns": columns,
        "column_count": len(columns),
        "null_like_counts": null_counts,
        "preview": rows,
        "truncated": row_count >= max_rows,
    }
