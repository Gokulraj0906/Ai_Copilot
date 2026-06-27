"""merge 0001 and 001

Revision ID: 9389139cc467
Revises: 0001, 001
Create Date: 2026-06-26 20:15:13.514459
"""
from alembic import op
import sqlalchemy as sa


revision = '9389139cc467'
down_revision = ('0001', '001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass