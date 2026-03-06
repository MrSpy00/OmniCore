"""Data and mass file manipulation toolkit."""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


def _resolve_sandboxed(path_str: str) -> Path:
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


class DataBatchRename(BaseTool):
    name = "data_batch_rename"
    description = "Rename many files using a regex replacement pattern."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        root = str(self._first_param(params, "root", "path", default="."))
        pattern = str(self._first_param(params, "pattern", default=""))
        replacement = str(self._first_param(params, "replacement", default=""))
        if not pattern:
            return self._failure("pattern is required")
        try:
            renamed = await asyncio.to_thread(
                _batch_rename, _resolve_sandboxed(root), pattern, replacement
            )
            return self._success("Batch rename completed", data={"renamed": renamed})
        except Exception as exc:
            return self._failure(str(exc))


class DataFindDuplicates(BaseTool):
    name = "data_find_duplicates"
    description = "Hash files in a directory and list exact duplicates."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        root = str(self._first_param(params, "root", "path", default="."))
        try:
            duplicates = await asyncio.to_thread(_find_duplicates, _resolve_sandboxed(root))
            return self._success("Duplicate scan completed", data={"duplicates": duplicates})
        except Exception as exc:
            return self._failure(str(exc))


class DataExcelToJson(BaseTool):
    name = "data_excel_to_json"
    description = "Convert Excel sheets into structured JSON rows."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path = str(self._first_param(params, "path", "file_path", default=""))
        if not path:
            return self._failure("path is required")
        try:
            data = await asyncio.to_thread(_excel_to_json, _resolve_sandboxed(path))
            return self._success("Excel converted to JSON", data={"sheets": data})
        except Exception as exc:
            return self._failure(str(exc))


class DataQueryCsvSql(BaseTool):
    name = "data_query_csv_sql"
    description = "Load a CSV into in-memory SQLite and query it with SQL."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        path = str(self._first_param(params, "path", "file_path", default=""))
        query = str(self._first_param(params, "query", "sql", default=""))
        if not path or not query:
            return self._failure("path and query are required")
        try:
            rows = await asyncio.to_thread(_query_csv_sql, _resolve_sandboxed(path), query)
            return self._success("CSV SQL query completed", data={"rows": rows})
        except Exception as exc:
            return self._failure(str(exc))


class DataZipAndEncrypt(BaseTool):
    name = "data_zip_and_encrypt"
    description = "Zip a directory and encrypt the archive with a password."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        source = str(self._first_param(params, "source", "path", default=""))
        password = str(self._first_param(params, "password", default=""))
        output_path = str(self._first_param(params, "output_path", default="archive.zip.enc"))
        if not source or not password:
            return self._failure("source and password are required")
        try:
            final_path = await asyncio.to_thread(
                _zip_and_encrypt,
                _resolve_sandboxed(source),
                _resolve_sandboxed(output_path),
                password,
            )
            return self._success("Archive zipped and encrypted", data={"path": str(final_path)})
        except Exception as exc:
            return self._failure(str(exc))


def _batch_rename(root: Path, pattern: str, replacement: str) -> list[dict[str, str]]:
    renamed: list[dict[str, str]] = []
    for item in root.iterdir():
        new_name = re.sub(pattern, replacement, item.name)
        if new_name != item.name:
            target = item.with_name(new_name)
            item.rename(target)
            renamed.append({"old": item.name, "new": target.name})
    return renamed


def _find_duplicates(root: Path) -> list[list[str]]:
    buckets: dict[str, list[str]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        buckets.setdefault(digest, []).append(str(path))
    return [paths for paths in buckets.values() if len(paths) > 1]


def _excel_to_json(path: Path) -> dict[str, list[dict[str, object]]]:
    workbook = pd.read_excel(path, sheet_name=None)
    return {name: frame.fillna("").to_dict(orient="records") for name, frame in workbook.items()}


def _query_csv_sql(path: Path, query: str) -> list[dict[str, object]]:
    frame = pd.read_csv(path)
    conn = sqlite3.connect(":memory:")
    try:
        frame.to_sql("data", conn, index=False, if_exists="replace")
        cursor = conn.execute(query)
        columns = [col[0] for col in cursor.description or []]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


def _zip_and_encrypt(source: Path, output_path: Path, password: str) -> Path:
    temp_zip = output_path.with_suffix(".zip")
    with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in source.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(source))

    key = Fernet.generate_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(temp_zip.read_bytes())
    output_path.write_bytes(encrypted)
    temp_zip.unlink(missing_ok=True)
    key_path = output_path.with_suffix(output_path.suffix + ".key")
    key_path.write_text(key.decode("utf-8") + "\n" + password, encoding="utf-8")
    return output_path
