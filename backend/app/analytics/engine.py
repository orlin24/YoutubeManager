"""Analytics engine: pure aggregation over analytics_snapshots.

Never fabricates data - if there are no snapshots, arrays are empty / zeros.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.video import Video

RANGES = {"7d": 7, "28d": 28, "90d": 90, "365d": 365}


def _window(range_key: str, start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    if range_key == "custom" and start and end:
        try:
            start_d = date.fromisoformat(start)
            end_d = date.fromisoformat(end)
            if start_d > end_d:
                start_d, end_d = end_d, start_d
            return start_d, end_d
        except ValueError:
            return today - timedelta(days=28), today
    days = RANGES.get(range_key, 28)
    return today - timedelta(days=days), today


def _rows(db: Session, channel_id: str, video_id: str | None, start_d: date, end_d: date):
    q = db.query(AnalyticsSnapshot).filter(
        AnalyticsSnapshot.channel_id == channel_id,
        AnalyticsSnapshot.date >= start_d,
        AnalyticsSnapshot.date <= end_d,
    )
    if video_id is not None:
        q = q.filter(AnalyticsSnapshot.video_id == video_id)
    else:
        q = q.filter(AnalyticsSnapshot.video_id.is_(None))
    return q.all()


def compute_range(
    db: Session,
    channel_id: str,
    range_key: str = "28d",
    start: str | None = None,
    end: str | None = None,
    video_id: str | None = None,
) -> dict:
    start_d, end_d = _window(range_key, start, end)
    rows = _rows(db, channel_id, video_id, start_d, end_d)

    overview = {
        "views": sum(r.views for r in rows),
        "watch_time_seconds": sum(r.watch_time_seconds for r in rows),
        "subscribers_gained": sum(r.subscribers_gained for r in rows),
        "subscribers_lost": sum(r.subscribers_lost for r in rows),
        "likes": sum(r.likes for r in rows),
        "comments": sum(r.comments for r in rows),
        "shares": sum(r.shares for r in rows),
        "average_view_duration_seconds": _avg([r.average_view_duration_seconds for r in rows]),
        "estimated_revenue": sum(r.estimated_revenue for r in rows if r.estimated_revenue is not None)
        or None,
    }

    by_date: dict[date, list[AnalyticsSnapshot]] = {}
    for r in rows:
        by_date.setdefault(r.date, []).append(r)

    timeseries = []
    cur = start_d
    while cur <= end_d:
        day_rows = by_date.get(cur, [])
        timeseries.append(
            {
                "date": cur.isoformat(),
                "views": sum(r.views for r in day_rows),
                "watch_time_seconds": sum(r.watch_time_seconds for r in day_rows),
                "subscribers_gained": sum(r.subscribers_gained for r in day_rows),
                "estimated_revenue": sum(
                    r.estimated_revenue for r in day_rows if r.estimated_revenue is not None
                )
                or None,
            }
        )
        cur += timedelta(days=1)

    growth = _growth(db, channel_id, video_id, start_d, end_d)
    return {"overview": overview, "timeseries": timeseries, "growth": growth}


def _growth(
    db: Session, channel_id: str, video_id: str | None, start_d: date, end_d: date
) -> dict:
    span = (end_d - start_d).days + 1
    prev_start = start_d - timedelta(days=span)
    prev_end = start_d - timedelta(days=1)
    cur = _rows(db, channel_id, video_id, start_d, end_d)
    prev = _rows(db, channel_id, video_id, prev_start, prev_end)

    cur_views = sum(r.views for r in cur)
    prev_views = sum(r.views for r in prev)
    cur_subs = sum(r.subscribers_gained - r.subscribers_lost for r in cur)
    prev_subs = sum(r.subscribers_gained - r.subscribers_lost for r in prev)

    return {
        "views_delta": cur_views - prev_views,
        "subscribers_delta": cur_subs - prev_subs,
        "views_pct": _pct(cur_views, prev_views),
        "subscribers_pct": _pct(cur_subs, prev_subs),
    }


def _pct(cur: float, prev: float) -> float | None:
    if prev == 0:
        return None if cur == 0 else 100.0
    return round((cur - prev) / prev * 100, 2)


def _avg(values: list[float | None]) -> float:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def top_videos(db: Session, channel_id: str, limit: int = 5, worst: bool = False) -> list[dict]:
    q = db.query(Video).filter(Video.channel_id == channel_id, Video.privacy_status != "private")
    q = q.order_by(Video.view_count.asc() if worst else Video.view_count.desc())
    videos = q.limit(limit).all()
    return [
        {
            "id": v.id,
            "youtube_video_id": v.youtube_video_id,
            "title": v.title,
            "thumbnail_url": v.thumbnail_url,
            "published_at": v.published_at.isoformat() if v.published_at else None,
            "view_count": v.view_count,
            "like_count": v.like_count,
            "comment_count": v.comment_count,
            "ctr": v.ctr,
            "average_view_duration_seconds": v.average_view_duration_seconds,
            "ai_score": v.ai_score,
            "privacy_status": v.privacy_status,
            "duration_seconds": v.duration_seconds,
            "description": v.description,
            "channel_id": v.channel_id,
        }
        for v in videos
    ]
