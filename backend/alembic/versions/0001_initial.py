"""initial schema

Revision ID: 0001
Revises:
Create Date: 2025-01-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "youtube_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("google_account_email", sa.String(length=320), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=False),
        sa.Column("channel_title", sa.String(length=255), nullable=False),
        sa.Column("channel_description", sa.Text(), nullable=False),
        sa.Column("channel_thumbnail", sa.String(length=500), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_youtube_accounts_user_id", "youtube_accounts", ["user_id"])
    op.create_index("ix_youtube_accounts_channel_id", "youtube_accounts", ["channel_id"], unique=True)

    op.create_table(
        "channels",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("youtube_account_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=False),
        sa.Column("subscriber_count", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["youtube_account_id"], ["youtube_accounts.id"]),
    )
    op.create_index("ix_channels_youtube_account_id", "channels", ["youtube_account_id"], unique=True)
    op.create_index("ix_channels_channel_id", "channels", ["channel_id"], unique=True)

    op.create_table(
        "videos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False),
        sa.Column("comment_count", sa.Integer(), nullable=False),
        sa.Column("privacy_status", sa.String(length=20), nullable=False),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("average_view_duration_seconds", sa.Float(), nullable=True),
        sa.Column("ai_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.UniqueConstraint("channel_id", "youtube_video_id", name="uq_videos_channel_ytid"),
    )
    op.create_index("ix_videos_channel_id", "videos", ["channel_id"])
    op.create_index("ix_videos_youtube_video_id", "videos", ["youtube_video_id"])

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False),
        sa.Column("watch_time_seconds", sa.Float(), nullable=False),
        sa.Column("average_view_duration_seconds", sa.Float(), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False),
        sa.Column("comments", sa.Integer(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("subscribers_gained", sa.Integer(), nullable=False),
        sa.Column("subscribers_lost", sa.Integer(), nullable=False),
        sa.Column("estimated_revenue", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.UniqueConstraint("channel_id", "video_id", "date", name="uq_snapshots_channel_video_date"),
    )
    op.create_index("ix_analytics_snapshots_channel_id", "analytics_snapshots", ["channel_id"])

    op.create_table(
        "ai_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=True),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
    )

    op.create_table(
        "ai_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=True),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("decision_type", sa.String(length=80), nullable=False),
        sa.Column("reasoning_summary", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["ai_tasks.id"]),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=True),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("proposed_change", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("channel_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("result", sa.String(length=80), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )

    op.create_table(
        "content_plan_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("idea", sa.Text(), nullable=True),
        sa.Column("target_keyword", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("publish_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
    )
    op.create_index("ix_content_plan_items_channel_id", "content_plan_items", ["channel_id"])

    op.create_table(
        "channel_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("niche", sa.String(length=255), nullable=True),
        sa.Column("target_audience", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=80), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("content_style", sa.String(length=255), nullable=True),
        sa.Column("upload_frequency", sa.String(length=80), nullable=True),
        sa.Column("brand_rules", sa.Text(), nullable=True),
        sa.Column("successful_titles", sa.JSON(), nullable=True),
        sa.Column("failed_topics", sa.JSON(), nullable=True),
        sa.Column("historical_performance", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"]),
    )
    op.create_index("ix_channel_profiles_channel_id", "channel_profiles", ["channel_id"], unique=True)

    op.create_table(
        "app_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("channel_profiles")
    op.drop_table("content_plan_items")
    op.drop_table("audit_logs")
    op.drop_table("approval_requests")
    op.drop_table("ai_decisions")
    op.drop_table("ai_tasks")
    op.drop_table("analytics_snapshots")
    op.drop_table("videos")
    op.drop_table("channels")
    op.drop_table("youtube_accounts")
    op.drop_table("users")
