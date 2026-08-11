from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("channel_id", "youtube_video_id", name="uq_videos_channel_ytid"),)

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True, nullable=False)
    youtube_video_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail_url: Mapped[str] = mapped_column(String(500), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    privacy_status: Mapped[str] = mapped_column(String(20), default="private")
    ctr: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_view_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    channel: Mapped["Channel"] = relationship(back_populates="videos")  # noqa: F821
    snapshots: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="video")  # noqa: F821
