"""AI Performance Score: a transparent, configurable 0-100 heuristic.

This is NOT an official YouTube metric. Each component metric is normalized
between 0 and 1, weighted, and summed. Missing metrics are skipped and weights
renormalized so the score stays in 0-100.
"""
from __future__ import annotations

from datetime import datetime, timezone

# Tuned for long-form content (e.g. music albums >1h): retention and watch
# time carry the most weight; CTR of ~6% is treated as strong.
DEFAULT_WEIGHTS = {
    "ctr": 0.20,
    "retention": 0.30,
    "views_velocity": 0.10,
    "subscriber_conversion": 0.10,
    "watch_time": 0.25,
    "engagement": 0.05,
}

METRIC_LABELS = {
    "ctr": "Click-through rate (CTR)",
    "retention": "Average view duration",
    "views_velocity": "Views velocity",
    "subscriber_conversion": "Subscriber conversion",
    "watch_time": "Total watch time",
    "engagement": "Engagement (likes + comments)",
}

_HIGH = 0.6
_LOW = 0.4


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def compute_video_score(video, snapshot_agg: dict | None = None, weights: dict | None = None) -> dict:
    """video: Video model or dict with attribute-like access.

    snapshot_agg: optional dict with channel-level aggregates for context
    (subscribers_gained, views, likes, comments).
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: v for k, v in weights.items() if k in w})

    views = float(getattr(video, "view_count", 0) or 0)
    ctr = getattr(video, "ctr", None)
    avg_dur = getattr(video, "average_view_duration_seconds", None)

    published = getattr(video, "published_at", None)
    age_days = 1.0
    if published:
        try:
            if isinstance(published, str):
                published = datetime.fromisoformat(published.replace("Z", "+00:00"))
            age_days = max(
                1.0, (datetime.now(timezone.utc) - published).total_seconds() / 86400.0
            )
        except (TypeError, ValueError):
            age_days = 1.0

    snap = snapshot_agg or {}
    subs_gained = float(snap.get("subscribers_gained", 0) or 0)
    snap_views = float(snap.get("views", 0) or 0)
    likes = float(getattr(video, "like_count", 0) or 0)
    comments = float(getattr(video, "comment_count", 0) or 0)
    watch_time = float(snap.get("watch_time_seconds", 0) or 0)

    duration = float(getattr(video, "duration_seconds", 0) or 0)
    is_long_form = duration > 60  # e.g. 1h+ music albums

    # normalized component scores 0..1
    components: dict[str, float] = {}
    if ctr is not None:
        # 8% CTR == perfect; 6% (user's benchmark for a good video) scores ~0.75
        components["ctr"] = _clamp(float(ctr) / 0.08)
    if avg_dur is not None:
        if is_long_form:
            # long-form: perfect when viewers watch ~50% of the video on average
            components["retention"] = _clamp((float(avg_dur) / duration) / 0.50)
        else:
            components["retention"] = _clamp(float(avg_dur) / 360.0)  # 6 min == perfect
    if views > 0:
        velocity = views / age_days
        components["views_velocity"] = _clamp(min(velocity / 1000.0, 1.0))  # 1k views/day == perfect
    if subs_gained > 0 and views > 0:
        conv = (subs_gained / views) * 1000.0
        components["subscriber_conversion"] = _clamp(conv / 5.0)  # 0.5% == perfect
    if watch_time > 0 and views > 0:
        per_view = watch_time / views
        if is_long_form:
            # long-form: per-view watch time relative to video duration
            components["watch_time"] = _clamp((per_view / duration) / 0.50)
        else:
            components["watch_time"] = _clamp(per_view / 360.0)
    if views > 0:
        eng = (likes + comments) / views
        components["engagement"] = _clamp(eng / 0.10)  # 10% engagement == perfect

    if not components:
        return {
            "score": None,
            "strengths": [],
            "weaknesses": ["Not enough data to compute a score yet."],
            "ai": False,
            "explanation": "Missing metrics (views, CTR, retention).",
        }

    total_w = sum(w[k] for k in components)
    score = round(sum(w[k] * components[k] for k in components) / total_w * 100, 1) if total_w else 0.0

    strengths = [
        METRIC_LABELS[k] for k, v in components.items() if v >= _HIGH
    ]
    weaknesses = [METRIC_LABELS[k] for k, v in components.items() if v < _LOW]

    return {
        "score": score,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "ai": False,
        "explanation": "Heuristic score from CTR, retention, velocity, conversion, watch time and engagement.",
    }
