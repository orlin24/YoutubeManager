from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class AiDecision(Base):
    __tablename__ = "ai_decisions"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("ai_tasks.id"), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
