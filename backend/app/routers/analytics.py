"""Analytics endpoints: channel-level and per-video ranges."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.routers.deps import get_user_channel
from app.services.analytics_service import compute_channel_analytics, compute_video_analytics
from app.utils.errors import AppError

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/channel")
def channel_analytics(channel_id: str, range: str = "28d", start: str | None = None,
                      end: str | None = None, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict:
    if range not in ("7d", "28d", "90d", "365d", "custom"):
        raise AppError(422, "VALIDATION_ERROR", "range must be one of 7d, 28d, 90d, 365d, custom.")
    ch = get_user_channel(db, user, channel_id)
    return compute_channel_analytics(db, ch.id, range, start, end)


@router.get("/traffic-sources")
async def traffic_sources(channel_id: str, days: int = 28,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)) -> dict:
    """Views broken down by traffic source (recommendations, search, external...)."""
    import asyncio

    from app.routers.deps import get_user_account
    from app.services.youtube_service import YouTubeService
    from app.youtube.client import get_analytics_client

    days = min(max(days, 1), 365)
    account = get_user_account(db, user, channel_id)
    service = YouTubeService()
    client = await asyncio.to_thread(get_analytics_client, db, account)
    items = await asyncio.to_thread(service.get_traffic_sources, client, account.channel_id, days)
    return {"items": items, "total_views": sum(i["views"] for i in items)}


@router.get("/realtime")
async def realtime_views(channel_id: str, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> dict:
    """Daily channel views for the last 7 days, from the YouTube Analytics API."""
    import asyncio

    from app.routers.deps import get_user_account
    from app.services.youtube_service import YouTubeService
    from app.youtube.client import get_analytics_client

    account = get_user_account(db, user, channel_id)
    service = YouTubeService()
    client = await asyncio.to_thread(get_analytics_client, db, account)
    items = await asyncio.to_thread(service.get_views_last_7d, client, account.channel_id)
    return {
        "items": items,
        "disclaimer": (
            "Jumlah penayangan berupa perkiraan saat pertama kali dilaporkan dan dapat "
            "disesuaikan seiring waktu saat data sudah lebih tersaring."
        ),
    }


@router.get("/video/{video_id}")
def video_analytics(video_id: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    return compute_video_analytics(db, video_id)
