from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposed_change: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(20), default="HIGH")  # LOW|MEDIUM|HIGH
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected|cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
