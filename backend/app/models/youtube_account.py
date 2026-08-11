from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, uuid_pk


class YouTubeAccount(Base):
    __tablename__ = "youtube_accounts"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    google_account_email: Mapped[str] = mapped_column(String(320), default="")
    channel_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), default="")
    channel_description: Mapped[str] = mapped_column(Text, default="")
    channel_thumbnail: Mapped[str] = mapped_column(String(500), default="")
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auth_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="accounts")  # noqa: F821
    channel: Mapped["Channel | None"] = relationship(back_populates="youtube_account", uselist=False)  # noqa: F821
