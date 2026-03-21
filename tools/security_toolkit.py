"""Security Toolkit — file encryption and decryption."""

from __future__ import annotations

import asyncio
import base64
from hashlib import sha256
from pathlib import Path

from cryptography.fernet import Fernet

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


def _derive_key(password: str) -> bytes:
    digest = sha256(password.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SecEncryptFile(BaseTool):
    name = "sec_encrypt_file"
    description = "Encrypt a file with a password (AES via Fernet)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        path = tool_input.parameters.get("path", "")
        password = tool_input.parameters.get("password", "")
        output_path = tool_input.parameters.get("output_path")
        if not path or not password:
            return self._failure("path and password are required")

        try:
            src = _resolve_sandboxed(path)
            data = await asyncio.to_thread(src.read_bytes)
            fernet = Fernet(_derive_key(password))
            encrypted = await asyncio.to_thread(fernet.encrypt, data)

            if output_path:
                dest = _resolve_sandboxed(output_path)
            else:
                dest = src.with_suffix(src.suffix + ".enc")
            await asyncio.to_thread(dest.write_bytes, encrypted)
            return self._success("File encrypted", data={"path": str(dest)})
        except Exception as exc:
            return self._failure(str(exc))


class SecDecryptFile(BaseTool):
    name = "sec_decrypt_file"
    description = "Decrypt a file with a password (AES via Fernet)."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        path = tool_input.parameters.get("path", "")
        password = tool_input.parameters.get("password", "")
        output_path = tool_input.parameters.get("output_path")
        if not path or not password:
            return self._failure("path and password are required")

        try:
            src = _resolve_sandboxed(path)
            data = await asyncio.to_thread(src.read_bytes)
            fernet = Fernet(_derive_key(password))
            decrypted = await asyncio.to_thread(fernet.decrypt, data)

            if output_path:
                dest = _resolve_sandboxed(output_path)
            else:
                dest = src.with_suffix("")
            await asyncio.to_thread(dest.write_bytes, decrypted)
            return self._success("File decrypted", data={"path": str(dest)})
        except Exception as exc:
            return self._failure(str(exc))
