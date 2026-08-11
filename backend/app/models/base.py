"""Declarative base + primary key helper."""
from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[str]:
    """UUID string primary key column."""
    return mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
