"""Tracks comments that have already been replied to, so the app can hide them
from the list. The comments are NOT deleted from YouTube - they are only hidden."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RepliedComment(Base):
    __tablename__ = "replied_comments"

    comment_id: Mapped[str] = mapped_column(Text, primary_key=True)  # YouTube comment id
    channel_id: Mapped[str] = mapped_column(Text, primary_key=True)  # internal Channel.id
    replied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
