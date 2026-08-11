"""channel_lifecycle + ai_patterns tables + channel_profiles.monetized

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channel_profiles", sa.Column("monetized", sa.Boolean(), nullable=True, server_default=sa.false()))
    op.create_table(
        "channel_lifecycle",
        sa.Column("channel_id", sa.Text(), primary_key=True),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("health_score", sa.Float(), nullable=True),
        sa.Column("growth_pct", sa.Float(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ai_patterns",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("pattern_type", sa.String(30), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_patterns_channel_id", "ai_patterns", ["channel_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_patterns_channel_id", table_name="ai_patterns")
    op.drop_table("ai_patterns")
    op.drop_table("channel_lifecycle")
    op.drop_column("channel_profiles", "monetized")
