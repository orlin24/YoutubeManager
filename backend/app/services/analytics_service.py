"""Analytics service: combines the analytics engine into API responses."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.analytics.engine import compute_range, top_videos


def compute_channel_analytics(
    db: Session,
    channel_id: str,
    range_key: str = "28d",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    result = compute_range(db, channel_id, range_key, start, end)
    result["top_videos"] = top_videos(db, channel_id, limit=5, worst=False)
    result["worst_videos"] = top_videos(db, channel_id, limit=5, worst=True)
    return result


def compute_video_analytics(db: Session, video_id: str, range_key: str = "28d") -> dict:
    from app.models.video import Video

    video = db.get(Video, video_id)
    if video is None:
        return {"overview": {}, "timeseries": []}
    result = compute_range(db, video.channel_id, range_key, video_id=video_id)
    # When no daily snapshots exist yet, fall back to the video's cumulative row
    # so the detail page always shows real numbers.
    if not result["timeseries"] and video.view_count > 0:
        avg_dur = video.average_view_duration_seconds or 0.0
        result["overview"] = {
            "views": video.view_count,
            "watch_time_seconds": avg_dur * video.view_count,
            "average_view_duration_seconds": avg_dur,
            "likes": video.like_count,
            "comments": video.comment_count,
            "shares": 0,
            "subscribers_gained": 0,
            "subscribers_lost": 0,
            "estimated_revenue": None,
        }
    result["video"] = {
        "id": video.id,
        "title": video.title,
        "youtube_video_id": video.youtube_video_id,
        "view_count": video.view_count,
        "like_count": video.like_count,
        "comment_count": video.comment_count,
    }
    return result
