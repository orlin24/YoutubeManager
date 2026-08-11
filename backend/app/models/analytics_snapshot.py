from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint("channel_id", "video_id", "date", name="uq_snapshots_channel_video_date"),
    )

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True, nullable=False)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    watch_time_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    average_view_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    subscribers_gained: Mapped[int] = mapped_column(Integer, default=0)
    subscribers_lost: Mapped[int] = mapped_column(Integer, default=0)
    estimated_revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    channel: Mapped["Channel"] = relationship(back_populates="snapshots")  # noqa: F821
    video: Mapped["Video | None"] = relationship(back_populates="snapshots")  # noqa: F821
