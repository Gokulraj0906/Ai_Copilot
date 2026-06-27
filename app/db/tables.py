# import uuid
# from sqlalchemy import String, DateTime, Boolean, func
# from sqlalchemy.dialects.postgresql import JSONB
# from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase


# class Base(DeclarativeBase):
#     pass


# class WorkflowRecord(Base):
#     __tablename__ = "workflows"

#     id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
#     name: Mapped[str] = mapped_column(String, default="Untitled")
#     data: Mapped[dict] = mapped_column(JSONB)
#     is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
#     created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())
#     updated_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# class SessionMessageRecord(Base):
#     __tablename__ = "session_messages"

#     id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
#     session_id: Mapped[str] = mapped_column(String, index=True)
#     role: Mapped[str] = mapped_column(String)
#     content: Mapped[str] = mapped_column(String)
#     created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())


# class AuditLogRecord(Base):
#     __tablename__ = "audit_logs"

#     id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
#     request_id: Mapped[str] = mapped_column(String, index=True)
#     action: Mapped[str] = mapped_column(String)
#     input_data: Mapped[dict] = mapped_column(JSONB)
#     llm_model: Mapped[str] = mapped_column(String)
#     raw_response: Mapped[str] = mapped_column(String)
#     created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())



import uuid
from sqlalchemy import String, DateTime, Boolean, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    """One row per user account."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    credentials: Mapped[list["CredentialRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    workflows: Mapped[list["WorkflowRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class CredentialRecord(Base):
    """
    One row per integration credential per user.

    service_name  — e.g. "slack", "razorpay", "whatsapp"
    credential_key — e.g. "bot_token", "key_id", "key_secret"
    encrypted_value — AES-256-GCM encrypted; only decrypted at execution time.
    """
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    service_name: Mapped[str] = mapped_column(String, nullable=False)   # e.g. "slack"
    credential_key: Mapped[str] = mapped_column(String, nullable=False) # e.g. "bot_token"
    encrypted_value: Mapped[str] = mapped_column(String, nullable=False) # AES-256-GCM ciphertext
    label: Mapped[str] = mapped_column(String, default="")              # user-friendly name
    created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["UserRecord"] = relationship(back_populates="credentials")

    __table_args__ = (
        # One value per (user, service, key) — enforce uniqueness
        Index("ix_credentials_user_service_key", "user_id", "service_name", "credential_key", unique=True),
    )


class WorkflowRecord(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, default="Untitled")
    data: Mapped[dict] = mapped_column(JSONB)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    user: Mapped["UserRecord"] = relationship(back_populates="workflows")


class SessionMessageRecord(Base):
    __tablename__ = "session_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    input_data: Mapped[dict] = mapped_column(JSONB)
    llm_model: Mapped[str] = mapped_column(String)
    raw_response: Mapped[str] = mapped_column(String)
    created_at: Mapped["DateTime"] = mapped_column(DateTime, server_default=func.now())