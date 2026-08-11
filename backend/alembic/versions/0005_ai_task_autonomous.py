"""AiTask: risk_level, deadline, idempotency_key

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_tasks", sa.Column("risk_level", sa.String(10), nullable=True, server_default="LOW"))
    op.add_column("ai_tasks", sa.Column("deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_tasks", sa.Column("idempotency_key", sa.String(160), nullable=True))
    op.create_index("ix_ai_tasks_idempotency_key", "ai_tasks", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_ai_tasks_idempotency_key", table_name="ai_tasks")
    op.drop_column("ai_tasks", "idempotency_key")
    op.drop_column("ai_tasks", "deadline")
    op.drop_column("ai_tasks", "risk_level")
