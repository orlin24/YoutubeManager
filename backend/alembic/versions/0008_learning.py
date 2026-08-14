"""learning tables: recommendation_outcomes + learning_memories

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.Text(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("decision", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=True),
        sa.Column("expected_outcome", sa.String(300), nullable=True),
        sa.Column("expected_value", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("actual_value", sa.Float(), nullable=True),
        sa.Column("actual_outcome", sa.String(300), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recommendation_outcomes_channel_id", "recommendation_outcomes", ["channel_id"])
    op.create_index("ix_recommendation_outcomes_status", "recommendation_outcomes", ["status"])

    op.create_table(
        "learning_memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.Text(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("pattern", sa.String(300), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("performance", sa.String(200), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learning_memories_channel_id", "learning_memories", ["channel_id"])
    op.create_index("ix_learning_memories_kind", "learning_memories", ["kind"])


def downgrade() -> None:
    op.drop_table("learning_memories")
    op.drop_table("recommendation_outcomes")
