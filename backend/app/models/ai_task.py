from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class AiTask(Base):
    __tablename__ = "ai_tasks"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # queued|running|waiting_approval|completed|failed|cancelled
    priority: Mapped[int] = mapped_column(Integer, default=5)
    risk_level: Mapped[str] = mapped_column(String(10), default="LOW")  # LOW|MEDIUM|HIGH|CRITICAL
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
