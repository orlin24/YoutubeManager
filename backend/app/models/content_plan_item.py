from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk

CONTENT_PLAN_STATUSES = (
    "IDEA", "DRAFT", "READY", "APPROVAL", "SCHEDULED", "PUBLISHED", "CANCELLED",
)


class ContentPlanItem(Base):
    __tablename__ = "content_plan_items"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    idea: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="IDEA")
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    channel: Mapped["Channel"] = relationship(back_populates="content_plan_items")  # noqa: F821
