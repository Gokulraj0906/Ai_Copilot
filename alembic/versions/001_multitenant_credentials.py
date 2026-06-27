"""Add users and credentials tables; add user_id to all existing tables

Revision ID: 001
Revises:
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ── users ──────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── credentials ────────────────────────────────────────────────
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("credential_key", sa.String(), nullable=False),
        sa.Column("encrypted_value", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_credentials_user_service_key",
        "credentials",
        ["user_id", "service_name", "credential_key"],
        unique=True,
    )

    # ── add user_id to existing tables ─────────────────────────────
    for table in ("workflows", "session_messages", "audit_logs"):
        op.add_column(
            table,
            sa.Column("user_id", sa.String(), nullable=True),
        )
        # Back-fill existing rows with a placeholder user_id
        op.execute(f"UPDATE {table} SET user_id = 'system' WHERE user_id IS NULL")
        op.alter_column(table, "user_id", nullable=False)
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # workflows — add FK after back-fill (system user won't exist,
    # but we don't add FK to allow legacy rows; enforce at app layer)


def downgrade():
    for table in ("workflows", "session_messages", "audit_logs"):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")

    op.drop_index("ix_credentials_user_service_key", table_name="credentials")
    op.drop_table("credentials")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")