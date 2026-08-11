"""channel_profiles: upload_cadence_days + last_reminder_at

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channel_profiles", sa.Column("upload_cadence_days", sa.Integer(), nullable=True))
    op.add_column("channel_profiles", sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("channel_profiles", "last_reminder_at")
    op.drop_column("channel_profiles", "upload_cadence_days")
