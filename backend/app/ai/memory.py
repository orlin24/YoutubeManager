"""AI memory: channel profile (niche/audience/style) + context builder."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.engine import compute_range
from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.video import Video
from app.utils.errors import AppError


def get_profile(db: Session, channel_id: str) -> ChannelProfile | None:
    return db.query(ChannelProfile).filter_by(channel_id=channel_id).first()


def update_profile(db: Session, channel_id: str, data: dict) -> ChannelProfile:
    profile = get_profile(db, channel_id)
    allowed = {
        "niche", "target_audience", "language", "country", "content_style",
        "upload_frequency", "upload_cadence_days", "brand_rules", "successful_titles",
        "failed_topics", "historical_performance",
    }
    payload = {k: v for k, v in data.items() if k in allowed}
    if profile is None:
        profile = ChannelProfile(channel_id=channel_id, **payload)
        db.add(profile)
    else:
        for k, v in payload.items():
            setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return profile


def get_recent_comments(db: Session, channel: Channel, limit: int = 8) -> list[dict]:
    """Live comments from YouTube (bounded, fails soft). Used to make the
    comment assistant actually see what viewers wrote."""
    from app.models.youtube_account import YouTubeAccount
    from app.models.video import Video
    from app.services.youtube_service import YouTubeService
    from app.youtube.client import get_authenticated_client

    account = db.get(YouTubeAccount, channel.youtube_account_id)
    if account is None:
        return []
    recent = (
        db.query(Video.youtube_video_id)
        .filter(Video.channel_id == channel.id, Video.comment_count > 0)
        .order_by(Video.comment_count.desc())
        .limit(5)
        .all()
    )
    if not recent:  # fallback: no synced comment counts yet
        recent = (
            db.query(Video.youtube_video_id)
            .filter(Video.channel_id == channel.id)
            .order_by(Video.published_at.desc())
            .limit(5)
            .all()
        )
    try:
        client = get_authenticated_client(db, account)
        items = YouTubeService().get_comments(
            client, video_id=None, max_results=limit, video_ids=[r[0] for r in recent]
        )
    except Exception:  # noqa: BLE001 - offline / token expired
        return []
    from app.models.replied_comment import RepliedComment

    replied = {
        r[0]
        for r in db.query(RepliedComment.comment_id)
        .filter(RepliedComment.channel_id == channel.id)
        .all()
    }
    return [c for c in items if c["id"] not in replied]
    yids = {c.get("video_id") for c in items if c.get("video_id")}
    if yids:
        titles = {
            v.youtube_video_id: v.title
            for v in db.query(Video).filter(Video.youtube_video_id.in_(yids)).all()
        }
        for c in items:
            c["video_title"] = titles.get(c.get("video_id"), "")
    return items


def get_traffic_sources(db: Session, channel: Channel, days: int = 28) -> list[dict]:
    """Live views-by-traffic-source for the AI context (fails soft)."""
    from app.models.youtube_account import YouTubeAccount
    from app.services.youtube_service import YouTubeService
    from app.youtube.client import get_analytics_client

    account = db.get(YouTubeAccount, channel.youtube_account_id)
    if account is None:
        return []
    try:
        client = get_analytics_client(db, account)
        return YouTubeService().get_traffic_sources(client, account.channel_id, days)
    except Exception:  # noqa: BLE001
        return []


def build_context(
    db: Session, channel: Channel, instruction: str, include_comments: bool = False,
    include_traffic: bool = False,
) -> dict:
    """Build the AI context block. Never dumps the whole database."""
    profile = get_profile(db, channel.id)
    today = date.today()
    recent = compute_range(db, channel.id, "28d")
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel.id)
        .order_by(Video.published_at.desc().nullslast())
        .limit(5)
        .all()
    )
    videos_out = [
        {
            "title": v.title,
            "youtube_video_id": v.youtube_video_id,
            "views": v.view_count,
            "likes": v.like_count,
            "comments": v.comment_count,
            "ctr": v.ctr,
            "avg_view_duration_seconds": v.average_view_duration_seconds,
            "ai_score": v.ai_score,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "privacy_status": v.privacy_status,
        }
        for v in videos
    ]
    return {
        "channel_profile": {
            "title": channel.title,
            "subscriber_count": channel.subscriber_count,
            "view_count": channel.view_count,
            "video_count": channel.video_count,
            "niche": profile.niche if profile else None,
            "target_audience": profile.target_audience if profile else None,
            "language": profile.language if profile else None,
            "country": profile.country if profile else None,
            "content_style": profile.content_style if profile else None,
            "upload_frequency": profile.upload_frequency if profile else None,
            "brand_rules": profile.brand_rules if profile else None,
            "successful_titles": (profile.successful_titles if profile and profile.successful_titles else []),
            "failed_topics": (profile.failed_topics if profile and profile.failed_topics else []),
        },
        "recent_performance": {
            "window": "last 28 days",
            "views": recent["overview"]["views"],
            "subscribers_gained": recent["overview"]["subscribers_gained"],
            "subscribers_lost": recent["overview"]["subscribers_lost"],
            "likes": recent["overview"]["likes"],
            "comments": recent["overview"]["comments"],
            "watch_time_seconds": recent["overview"]["watch_time_seconds"],
            "estimated_revenue": recent["overview"]["estimated_revenue"],
            "growth": recent["growth"],
        },
        "recent_videos": videos_out,
        "recent_comments": get_recent_comments(db, channel, limit=8) if include_comments else [],
        "traffic_sources": get_traffic_sources(db, channel) if include_traffic else [],
        "user_instruction": instruction,
        "today": today.isoformat(),
    }


def require_channel(db: Session, channel_id: str) -> Channel:
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise AppError(404, "NOT_FOUND", "Channel not found.")
    return channel
