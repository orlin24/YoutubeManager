"""Content Factory tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_ideas",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("angle", sa.Text(), nullable=True),
        sa.Column("format", sa.String(60), nullable=True),
        sa.Column("target_audience", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_ideas_channel_id", "content_ideas", ["channel_id"])
    op.create_table(
        "content_briefs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("idea_id", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("title_concept", sa.Text(), nullable=True),
        sa.Column("audience", sa.Text(), nullable=True),
        sa.Column("angle", sa.Text(), nullable=True),
        sa.Column("format", sa.String(60), nullable=True),
        sa.Column("duration", sa.String(40), nullable=True),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("structure", sa.JSON(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("visual_direction", sa.Text(), nullable=True),
        sa.Column("thumbnail_concept", sa.Text(), nullable=True),
        sa.Column("seo_keywords", sa.JSON(), nullable=True),
        sa.Column("production_notes", sa.Text(), nullable=True),
        sa.Column("quality_requirements", sa.Text(), nullable=True),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("niche", sa.String(40), nullable=True),
        sa.Column("script_outline", sa.JSON(), nullable=True),
        sa.Column("title_variants", sa.JSON(), nullable=True),
        sa.Column("thumbnail_variants", sa.JSON(), nullable=True),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("quality_result", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_briefs_idea_id", "content_briefs", ["idea_id"])
    op.create_index("ix_content_briefs_channel_id", "content_briefs", ["channel_id"])
    op.create_table(
        "content_queue",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("idea_id", sa.Text(), nullable=True),
        sa.Column("brief_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(20), nullable=True),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("publish_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("youtube_video_id", sa.Text(), nullable=True),
        sa.Column("expected_views", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_content_queue_channel_id", "content_queue", ["channel_id"])
    op.create_table(
        "content_experiments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("queue_id", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("control", sa.Text(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=True),
        sa.Column("metric", sa.String(40), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_experiments_channel_id", "content_experiments", ["channel_id"])
    op.create_table(
        "content_performance",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("video_id", sa.Text(), nullable=False),
        sa.Column("checkpoint", sa.String(10), nullable=False),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("watch_time_seconds", sa.Integer(), nullable=True),
        sa.Column("retention", sa.Float(), nullable=True),
        sa.Column("subscribers_gained", sa.Integer(), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("rpm", sa.Float(), nullable=True),
        sa.Column("traffic_source", sa.JSON(), nullable=True),
        sa.Column("expected_views", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_content_performance_video_id", "content_performance", ["video_id"])
    op.create_table(
        "content_generation_logs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("channel_id", sa.Text(), nullable=True),
        sa.Column("component", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    for t in ("content_generation_logs", "content_performance", "content_experiments",
              "content_queue", "content_briefs", "content_ideas"):
        op.drop_table(t)
