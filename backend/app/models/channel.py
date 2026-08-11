from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[str] = uuid_pk()
    youtube_account_id: Mapped[str] = mapped_column(
        ForeignKey("youtube_accounts.id"), unique=True, nullable=False
    )
    channel_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail_url: Mapped[str] = mapped_column(String(500), default="")
    subscriber_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    youtube_account: Mapped["YouTubeAccount"] = relationship(back_populates="channel")  # noqa: F821
    videos: Mapped[list["Video"]] = relationship(back_populates="channel")  # noqa: F821
    snapshots: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="channel")  # noqa: F821
    content_plan_items: Mapped[list["ContentPlanItem"]] = relationship(back_populates="channel")  # noqa: F821
    profile: Mapped["ChannelProfile | None"] = relationship(  # noqa: F821
        back_populates="channel", uselist=False
    )
