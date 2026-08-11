"""Business Intelligence: forecast history for evaluation & learning."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ForecastHistory(Base):
    __tablename__ = "forecast_history"
    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: __import__("uuid").uuid4().hex)
    metric: Mapped[str] = mapped_column(String(20))  # views|subscribers|watch_time|revenue
    channel_id: Mapped[str] = mapped_column(Text, index=True)
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    target_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predicted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100
    model_version: Mapped[str] = mapped_column(String(40), default="forecast_v1")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assumptions: Mapped[str] = mapped_column(Text, default="")
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[float | None] = mapped_column(Float, nullable=True)  # signed pct
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
