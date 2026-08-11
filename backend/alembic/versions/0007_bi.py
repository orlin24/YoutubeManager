"""forecast_history

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_history",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("metric", sa.String(20), nullable=False),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("forecast_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=True),
        sa.Column("lower_bound", sa.Float(), nullable=True),
        sa.Column("upper_bound", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(40), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assumptions", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("error", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_forecast_history_channel_id", "forecast_history", ["channel_id"])
    op.create_index("ix_forecast_history_forecast_date", "forecast_history", ["forecast_date"])


def downgrade() -> None:
    op.drop_table("forecast_history")
