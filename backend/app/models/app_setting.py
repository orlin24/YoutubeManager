from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, uuid_pk


class AppSetting(Base):
    """Key/value persisted settings (e.g. user-editable score weights)."""

    __tablename__ = "app_settings"

    id: Mapped[str] = uuid_pk()
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
