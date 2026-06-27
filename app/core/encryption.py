"""
AES-256-GCM encryption for user credentials.

Reads ENCRYPTION_MASTER_KEY via settings (pydantic-settings loads .env properly).
Do NOT use os.getenv() here — pydantic-settings v2 requires model_config,
not the old inner Config class, to actually load the .env file.
"""

from __future__ import annotations

import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_aes: AESGCM | None = None
_cached_key: str = ""


def _get_key_hex() -> str:
    """Read key from settings (which loads .env) — never from os.getenv directly."""
    try:
        from app.core.config import settings  # local import avoids circular dep
        return (settings.encryption_master_key or "").strip()
    except Exception:
        return os.getenv("ENCRYPTION_MASTER_KEY", "").strip()


def _get_aes() -> AESGCM:
    global _aes, _cached_key

    key_hex = _get_key_hex()

    if _aes is not None and key_hex == _cached_key:
        return _aes

    if not key_hex:
        raise RuntimeError(
            "ENCRYPTION_MASTER_KEY is not set in your .env file.\n"
            "Generate one with:\n"
            "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
            "Then add to .env:\n"
            "  ENCRYPTION_MASTER_KEY=<your 64-char hex string>"
        )

    if len(key_hex) != 64:
        raise RuntimeError(
            f"ENCRYPTION_MASTER_KEY must be exactly 64 hex characters. "
            f"Yours is {len(key_hex)} characters."
        )

    try:
        key_bytes = bytes.fromhex(key_hex)
    except ValueError:
        raise RuntimeError(
            "ENCRYPTION_MASTER_KEY contains invalid characters — must be hex (0-9, a-f)."
        )

    _aes = AESGCM(key_bytes)
    _cached_key = key_hex
    return _aes


def encrypt(plaintext: str) -> str:
    aes = _get_aes()
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt(ciphertext_b64: str) -> str:
    aes = _get_aes()
    raw = base64.b64decode(ciphertext_b64)
    nonce, ct = raw[:12], raw[12:]
    return aes.decrypt(nonce, ct, None).decode()


def is_configured() -> bool:
    key_hex = _get_key_hex()
    if not key_hex or len(key_hex) != 64:
        return False
    try:
        bytes.fromhex(key_hex)
        return True
    except ValueError:
        return False
