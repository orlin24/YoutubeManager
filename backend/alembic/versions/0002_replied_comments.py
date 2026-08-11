"""replied_comments table + youtube_accounts.auth_error

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # idempotent cross-DB (Postgres & SQLite): beberapa env sudah menambah kolom manual
    from sqlalchemy import inspect
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("youtube_accounts")}
    if "auth_error" not in cols:
        op.add_column("youtube_accounts", sa.Column("auth_error", sa.Text(), nullable=True))
    op.create_table(
        "replied_comments",
        sa.Column("comment_id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), primary_key=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("replied_comments")
    op.drop_column("youtube_accounts", "auth_error")
