from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk


class ChannelProfile(Base):
    """AI memory for a channel: niche, audience, style, brand rules, history."""

    __tablename__ = "channel_profiles"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), unique=True, nullable=False)
    niche: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    content_style: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upload_frequency: Mapped[str | None] = mapped_column(String(80), nullable=True)
    upload_cadence_days: Mapped[int | None] = mapped_column(nullable=True)  # reminder: upload every N days
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monetized: Mapped[bool] = mapped_column(default=False)  # user-marked manually (no fake data)
    brand_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    successful_titles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    failed_topics: Mapped[list | None] = mapped_column(JSON, nullable=True)
    historical_performance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    channel: Mapped["Channel"] = relationship(back_populates="profile")  # noqa: F821
