"""Channel lifecycle: detected mode, objective, KPIs, and AI pattern records.

- ChannelLifecycle: latest detected lifecycle snapshot per channel (upsert).
- AiPattern: append-only records (winners, formulas, risks, recommendations,
  experiments) so the AI has memory of past findings.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChannelLifecycle(Base):
    __tablename__ = "channel_lifecycle"

    channel_id: Mapped[str] = mapped_column(Text, primary_key=True)  # Channel.id
    mode: Mapped[str] = mapped_column(String(20))  # NEW/GROWTH/MONETIZED/SCALE/RECOVERY
    objective: Mapped[str] = mapped_column(Text, default="")
    health_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    growth_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # KPIs, winners, priorities
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now().astimezone())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiPattern(Base):
    __tablename__ = "ai_patterns"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    pattern_type: Mapped[str] = mapped_column(String(30))  # winner/formula/risk/recommendation/experiment
    title: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(10), default="LOW")  # LOW/MEDIUM/HIGH
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
