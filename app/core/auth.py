# """
# JWT-based authentication.

# Flow:
#   1. POST /auth/register  → create user, return JWT
#   2. POST /auth/login     → verify password, return JWT
#   3. All protected endpoints use Depends(get_current_user) → returns UserRecord

# JWT contains:  {"sub": user_id, "exp": unix_timestamp}
# Signed with HS256 using JWT_SECRET from .env
# """

# from __future__ import annotations

# import os
# from datetime import datetime, timedelta, timezone

# from fastapi import Depends, Header, HTTPException
# from jose import JWTError, jwt
# from passlib.context import CryptContext
# from sqlalchemy import select
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.database import get_db
# from app.db.tables import UserRecord

# JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
# JWT_ALGORITHM = "HS256"
# JWT_EXPIRE_HOURS = 24 * 7   # 7 days

# _pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# # ─── Password helpers ─────────────────────────────────────────────────────────

# def hash_password(password: str) -> str:
#     return _pwd.hash(password)


# def verify_password(plain: str, hashed: str) -> bool:
#     return _pwd.verify(plain, hashed)


# # ─── JWT helpers ──────────────────────────────────────────────────────────────

# def create_token(user_id: str) -> str:
#     expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
#     return jwt.encode({"sub": user_id, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


# def decode_token(token: str) -> str:
#     """Returns user_id or raises HTTPException 401."""
#     try:
#         payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
#         user_id: str | None = payload.get("sub")
#         if not user_id:
#             raise HTTPException(status_code=401, detail="Invalid token")
#         return user_id
#     except JWTError:
#         raise HTTPException(status_code=401, detail="Invalid or expired token")


# # ─── FastAPI dependency ───────────────────────────────────────────────────────

# async def get_current_user(
#     authorization: str = Header(default=""),
#     db: AsyncSession = Depends(get_db),
# ) -> UserRecord:
#     """
#     FastAPI dependency — extracts and validates Bearer token,
#     returns the live UserRecord from DB.
#     Usage:  current_user: UserRecord = Depends(get_current_user)
#     """
#     if not authorization.startswith("Bearer "):
#         raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

#     token = authorization.removeprefix("Bearer ").strip()
#     user_id = decode_token(token)

#     user = await db.get(UserRecord, user_id)
#     if not user or not user.is_active:
#         raise HTTPException(status_code=401, detail="User not found or deactivated")
#     return user

"""
JWT-based authentication.

Flow:
  1. POST /auth/register  → create user, return JWT
  2. POST /auth/login     → verify password, return JWT
  3. All protected endpoints use Depends(get_current_user) → returns UserRecord
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.ext.asyncio import AsyncSession

# Import your validated settings instead of using os.getenv
from app.core.config import settings
from app.db.database import get_db
from app.db.tables import UserRecord

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7   # 7 days

# ─── Password helpers (Modernized with pwdlib) ────────────────────────────────

password_hash = PasswordHash((BcryptHasher(),))

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)

# ─── JWT helpers ──────────────────────────────────────────────────────────────

def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    # Using settings.jwt_secret here
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.jwt_secret, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> str:
    """Returns user_id or raises HTTPException 401."""
    try:
        # Using settings.jwt_secret here
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ─── FastAPI dependency ───────────────────────────────────────────────────────

async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> UserRecord:
    """
    FastAPI dependency — extracts and validates Bearer token,
    returns the live UserRecord from DB.
    Usage:  current_user: UserRecord = Depends(get_current_user)
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_token(token)

    # Note: If your user_id in the DB is a UUID, you might need to cast user_id back to UUID here
    user = await db.get(UserRecord, user_id)
    if not user or not getattr(user, "is_active", True):
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    return user