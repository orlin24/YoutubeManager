"""Shared router helpers: channel ownership scoping."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.channel import Channel
from app.models.user import User
from app.models.youtube_account import YouTubeAccount
from app.utils.errors import AppError


def user_channel_ids(db: Session, user: User) -> list[str]:
    rows = (
        db.query(Channel.id)
        .join(YouTubeAccount, YouTubeAccount.id == Channel.youtube_account_id)
        .filter(YouTubeAccount.user_id == user.id)
        .all()
    )
    return [r[0] for r in rows]


def get_user_channel(db: Session, user: User, channel_id: str) -> Channel:
    ids = user_channel_ids(db, user)
    if channel_id not in ids:
        raise AppError(404, "NOT_FOUND", "Channel not found.")
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise AppError(404, "NOT_FOUND", "Channel not found.")
    return channel


def get_user_account(db: Session, user: User, channel_id: str) -> YouTubeAccount:
    channel = get_user_channel(db, user, channel_id)
    account = channel.youtube_account
    if account is None:
        raise AppError(404, "NOT_FOUND", "YouTube account not found for this channel.")
    return account
