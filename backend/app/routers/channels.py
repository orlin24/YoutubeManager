"""Channels: list, detail, refresh sync, profile (AI memory)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.channel import Channel
from app.models.user import User
from app.models.video import Video
from app.routers.deps import get_user_account, get_user_channel, user_channel_ids
from app.services.analytics_service import compute_channel_analytics
from app.services.audit_service import log_audit
from app.services.youtube_service import sync_channel_data
from app.ai.memory import get_profile, update_profile
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.security import check_csrf

router = APIRouter(prefix="/channels", tags=["channels"])
logger = get_logger("channels")


def _channel_dict(ch: Channel) -> dict:
    return {
        "id": ch.id,
        "channel_id": ch.channel_id,
        "title": ch.title,
        "description": ch.description,
        "thumbnail_url": ch.thumbnail_url,
        "subscriber_count": ch.subscriber_count,
        "view_count": ch.view_count,
        "video_count": ch.video_count,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }


@router.get("")
def list_channels(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    channels = db.query(Channel).filter(Channel.id.in_(ids)).all() if ids else []
    # lifecycle mode per channel (cheap join for the UI badge)
    modes: dict[str, str] = {}
    if ids:
        from app.models.lifecycle import ChannelLifecycle

        for row in db.query(ChannelLifecycle).filter(ChannelLifecycle.channel_id.in_(ids)).all():
            modes[row.channel_id] = row.mode
    items = [_channel_dict(c) for c in channels]
    for it in items:
        it["lifecycle_mode"] = modes.get(it["id"])
    return {"items": items, "total": len(items)}


@router.get("/{channel_id}")
def get_channel(channel_id: str, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    ch = get_user_channel(db, user, channel_id)
    data = _channel_dict(ch)
    profile = get_profile(db, ch.id)
    data["profile"] = _profile_dict(profile)
    data["analytics"] = compute_channel_analytics(db, ch.id, "28d")["overview"]
    return data


def _profile_dict(profile) -> dict:
    if profile is None:
        return {}
    return {
        "niche": profile.niche,
        "target_audience": profile.target_audience,
        "language": profile.language,
        "country": profile.country,
        "content_style": profile.content_style,
        "upload_frequency": profile.upload_frequency,
        "upload_cadence_days": profile.upload_cadence_days,
        "brand_rules": profile.brand_rules,
        "successful_titles": profile.successful_titles or [],
        "failed_topics": profile.failed_topics or [],
        "historical_performance": profile.historical_performance or {},
    }


@router.post("/{channel_id}/refresh")
def refresh(channel_id: str, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    account = get_user_account(db, user, channel_id)
    result = sync_channel_data(db, account)
    return {"success": True, "synced_at": __import__("datetime").datetime.now().isoformat(),
            **result}


@router.get("/{channel_id}/videos")
def channel_videos(channel_id: str, limit: int = 50, offset: int = 0,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ch = get_user_channel(db, user, channel_id)
    q = db.query(Video).filter(Video.channel_id == ch.id).order_by(
        Video.published_at.desc().nullslast())
    total = q.count()
    videos = q.offset(offset).limit(min(limit, 100)).all()
    return {"items": [_video_dict(v) for v in videos], "total": total}


def _video_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "youtube_video_id": v.youtube_video_id,
        "title": v.title,
        "description": v.description,
        "thumbnail_url": v.thumbnail_url,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "duration_seconds": v.duration_seconds,
        "view_count": v.view_count,
        "like_count": v.like_count,
        "comment_count": v.comment_count,
        "privacy_status": v.privacy_status,
        "ctr": v.ctr,
        "average_view_duration_seconds": v.average_view_duration_seconds,
        "ai_score": v.ai_score,
        "channel_id": v.channel_id,
    }


@router.get("/{channel_id}/profile")
def channel_profile(channel_id: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    ch = get_user_channel(db, user, channel_id)
    return _profile_dict(get_profile(db, ch.id))


class ProfileUpdate(BaseModel):
    niche: str | None = None
    target_audience: str | None = None
    language: str | None = None
    country: str | None = None
    content_style: str | None = None
    upload_frequency: str | None = None
    upload_cadence_days: int | None = None
    brand_rules: str | None = None
    successful_titles: list | None = None
    failed_topics: list | None = None
    historical_performance: dict | None = None


@router.patch("/{channel_id}/profile")
def patch_profile(channel_id: str, payload: ProfileUpdate, request: Request,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, channel_id)
    data = payload.model_dump(exclude_none=True)
    profile = update_profile(db, ch.id, data)
    log_audit(db, user_id=user.id, channel_id=ch.id, action="channel_profile_updated",
              target=ch.title, result="ok")
    return _profile_dict(profile)
