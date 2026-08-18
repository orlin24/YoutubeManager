"""Automatic learning tables.

RecommendationOutcome: every AI recommendation gets an id so its expected vs
actual outcome can be compared after the evaluation period (audit #16).

LearningMemory       : durable memory kinds (audit #17):
    WINNING_PATTERN, FAILED_PATTERN, EXPERIMENT_RESULT, DECISION_OUTCOME,
    CONFIDENCE_HISTORY, STRATEGY_HISTORY.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk

LEARNING_KINDS = (
    "WINNING_PATTERN", "FAILED_PATTERN", "EXPERIMENT_RESULT",
    "DECISION_OUTCOME", "CONFIDENCE_HISTORY", "STRATEGY_HISTORY",
)


class RecommendationOutcome(Base):
    __tablename__ = "recommendation_outcomes"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)                 # e.g. "Uji format X"
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[str] = mapped_column(String(20), default="INSUFFICIENT_DATA")
    expected_outcome: Mapped[str] = mapped_column(String(300), default="")      # e.g. "+30% views"
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)  # normalized expected (views)
    status: Mapped[str] = mapped_column(String(20), default="pending")          # pending | evaluated
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_outcome: Mapped[str] = mapped_column(String(300), default="")
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LearningMemory(Base):
    __tablename__ = "learning_memories"

    id: Mapped[str] = uuid_pk()
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    pattern: Mapped[str] = mapped_column(String(300), nullable=False)           # human-readable pattern
    evidence: Mapped[str] = mapped_column(Text, default="")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)               # 0-100 internal
    performance: Mapped[str] = mapped_column(String(200), default="")           # e.g. "2.8x median channel"
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
