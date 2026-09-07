"""Security Toolkit — file encryption and decryption."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from hashlib import sha256
from pathlib import Path

from cryptography.fernet import Fernet

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path

# PBKDF2 parameters (OWASP 2023 recommendation for PBKDF2-SHA256)
_PBKDF2_ITERATIONS = 600_000
_SALT_SIZE = 16
_KEY_VERSION_PREFIX = b"v1:"  # 3-byte prefix to identify PBKDF2-encrypted data


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


def _derive_key(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a Fernet-compatible key using PBKDF2-SHA256.

    Returns (key, salt). If salt is None, a new random salt is generated.
    """
    if salt is None:
        salt = os.urandom(_SALT_SIZE)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS, dklen=32)
    return base64.urlsafe_b64encode(dk), salt


def _derive_key_legacy(password: str) -> bytes:
    """Legacy single-iteration SHA-256 key derivation (for decrypting old files)."""
    digest = sha256(password.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _encrypt_with_password(data: bytes, password: str) -> bytes:
    """Encrypt data with PBKDF2-derived key. Returns versioned ciphertext."""
    key, salt = _derive_key(password)
    encrypted = Fernet(key).encrypt(data)
    return _KEY_VERSION_PREFIX + salt + encrypted


def _decrypt_with_password(data: bytes, password: str) -> bytes:
    """Decrypt data, trying PBKDF2 (v1) first, then legacy SHA-256."""
    if data[:3] == _KEY_VERSION_PREFIX:
        salt = data[3 : 3 + _SALT_SIZE]
        ciphertext = data[3 + _SALT_SIZE :]
        key, _ = _derive_key(password, salt=salt)
        return Fernet(key).decrypt(ciphertext)
    legacy_key = _derive_key_legacy(password)
    return Fernet(legacy_key).decrypt(data)


class SecEncryptFile(BaseTool):
    name = "sec_encrypt_file"
    description = "Encrypt a file with a password (AES via Fernet with PBKDF2)."
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
            encrypted = await asyncio.to_thread(_encrypt_with_password, data, password)

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
    description = "Decrypt a file with a password (AES via Fernet with PBKDF2)."
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
            decrypted = await asyncio.to_thread(_decrypt_with_password, data, password)

            if output_path:
                dest = _resolve_sandboxed(output_path)
            else:
                dest = src.with_suffix("")
            await asyncio.to_thread(dest.write_bytes, decrypted)
            return self._success("File decrypted", data={"path": str(dest)})
        except Exception as exc:
            return self._failure(str(exc))
