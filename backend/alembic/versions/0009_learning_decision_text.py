"""widen recommendation_outcomes.decision to Text (full titles)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("recommendation_outcomes") as batch:
        batch.alter_column("decision", existing_type=sa.String(200), type_=sa.Text(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("recommendation_outcomes") as batch:
        batch.alter_column("decision", existing_type=sa.Text(), type_=sa.String(200), nullable=False)
