"""
Credential store — the single source of truth for user API keys.

How it works:
  1. User saves their Slack token via POST /credentials
  2. We encrypt it with AES-256-GCM and store in the credentials table
  3. At workflow execution time, get_user_credentials(user_id) decrypts
     and returns a flat dict:  {"slack.bot_token": "xoxb-...", ...}
  4. execution.py reads from this dict instead of global settings

Redis caching:
  Credentials are cached per user for 5 minutes (TTL=300s) so that
  with 10k users, a busy workflow doesn't hammer PostgreSQL on every node.
  Cache is invalidated on any credential update/delete.

Security properties:
  - Plaintext never written to disk or logs
  - DB stores only ciphertext — a DB dump is useless without master key
  - Master key lives only in server memory (from env var)
  - Each value has a unique nonce — identical keys have different ciphertexts
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt, encrypt
from app.db.tables import CredentialRecord

logger = logging.getLogger("copilot.credentials")

CACHE_TTL = 300   # seconds — credentials cached in Redis per user


# ─── Cache helpers (lazy import to avoid circular deps) ──────────────────────

async def _cache_get(user_id: str) -> dict | None:
    try:
        from app.core.cache import redis_client  # type: ignore
        raw = await redis_client.get(f"creds:{user_id}")
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def _cache_set(user_id: str, data: dict) -> None:
    try:
        from app.core.cache import redis_client  # type: ignore
        await redis_client.setex(f"creds:{user_id}", CACHE_TTL, json.dumps(data))
    except Exception:
        pass


async def _cache_del(user_id: str) -> None:
    try:
        from app.core.cache import redis_client  # type: ignore
        await redis_client.delete(f"creds:{user_id}")
    except Exception:
        pass


# ─── Public API ───────────────────────────────────────────────────────────────

async def get_user_credentials(user_id: str, db: AsyncSession) -> dict[str, str]:
    """
    Return all credentials for a user as a flat dict.
    Example:  {"slack.bot_token": "xoxb-...", "razorpay.key_id": "rzp_live_..."}

    Tries Redis cache first, falls back to PostgreSQL with decryption.
    """
    cached = await _cache_get(user_id)
    if cached is not None:
        return cached

    result = await db.execute(
        select(CredentialRecord).where(CredentialRecord.user_id == user_id)
    )
    records = result.scalars().all()

    creds: dict[str, str] = {}
    for rec in records:
        try:
            plaintext = decrypt(rec.encrypted_value)
            creds[f"{rec.service_name}.{rec.credential_key}"] = plaintext
        except Exception as e:
            logger.error(f"Failed to decrypt credential {rec.id} for user {user_id}: {e}")

    await _cache_set(user_id, creds)
    return creds


async def upsert_credential(
    user_id: str,
    service_name: str,
    credential_key: str,
    plaintext_value: str,
    label: str,
    db: AsyncSession,
) -> str:
    """
    Save or update a single credential. Encrypts before writing.
    Returns the credential record ID.
    """
    encrypted = encrypt(plaintext_value)

    result = await db.execute(
        select(CredentialRecord).where(
            CredentialRecord.user_id == user_id,
            CredentialRecord.service_name == service_name,
            CredentialRecord.credential_key == credential_key,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.encrypted_value = encrypted
        existing.label = label
        record_id = existing.id
    else:
        rec = CredentialRecord(
            user_id=user_id,
            service_name=service_name,
            credential_key=credential_key,
            encrypted_value=encrypted,
            label=label,
        )
        db.add(rec)
        await db.flush()
        record_id = rec.id

    await db.commit()
    await _cache_del(user_id)  # invalidate cache
    logger.info(f"Credential upserted: user={user_id} service={service_name} key={credential_key}")
    return record_id


async def delete_credential(
    user_id: str,
    service_name: str,
    credential_key: str,
    db: AsyncSession,
) -> bool:
    result = await db.execute(
        select(CredentialRecord).where(
            CredentialRecord.user_id == user_id,
            CredentialRecord.service_name == service_name,
            CredentialRecord.credential_key == credential_key,
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        return False
    await db.delete(rec)
    await db.commit()
    await _cache_del(user_id)
    return True


async def list_credentials(user_id: str, db: AsyncSession) -> list[dict]:
    """
    Return credential metadata (no plaintext values).
    Used for the "connected integrations" UI.
    """
    result = await db.execute(
        select(CredentialRecord).where(CredentialRecord.user_id == user_id)
    )
    return [
        {
            "id": r.id,
            "service_name": r.service_name,
            "credential_key": r.credential_key,
            "label": r.label,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in result.scalars().all()
    ]