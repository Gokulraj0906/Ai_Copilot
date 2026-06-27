"""
Auth routes:
  POST /auth/register   — create account
  POST /auth/login      — get JWT
  GET  /auth/me         — current user info
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_token, hash_password, verify_password, get_current_user
from app.db.database import get_db
from app.db.tables import UserRecord

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(UserRecord).where(UserRecord.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = UserRecord(email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_token(user.id)
    return {"user_id": user.id, "email": user.email, "token": token}


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserRecord).where(UserRecord.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    return {"user_id": user.id, "email": user.email, "token": create_token(user.id)}


@router.get("/me")
async def me(current_user: UserRecord = Depends(get_current_user)):
    return {"user_id": current_user.id, "email": current_user.email, "created_at": current_user.created_at.isoformat()}