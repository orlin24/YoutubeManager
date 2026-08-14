"""Backfill channel-level analytics_snapshots from the YouTube Analytics API.

Why: the Analytics API lags ~1-2 days, so the daily sync used to store zeros,
and history was lost at the last restore. This fills the last N finalized days
(real deltas) for every channel so ranges (7d/28d/90d) show actual numbers.

Usage (on the Pi, as the service user):
    cd /opt/ai-youtube-manager/backend && sudo -u aym .venv/bin/python scripts/backfill_analytics.py [days=120]
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from app.database import SessionLocal
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.channel import Channel
from app.models.youtube_account import YouTubeAccount
from app.services.config_store import apply_overrides
from app.utils.logging import get_logger
from app.youtube.client import AppError, get_analytics_client, safe_call

logger = get_logger("backfill_analytics")

METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,"
    "subscribersGained,subscribersLost,estimatedRevenue"
)


def fetch_daily(client, channel_id: str, start: date, end: date) -> dict[date, dict]:
    try:
        resp = safe_call(
            client.reports().query,
            ids=f"channel=={channel_id}",
            startDate=start.isoformat(),
            endDate=end.isoformat(),
            metrics=METRICS,
            dimensions="day",
        )
    except AppError as exc:
        # Accounts without the restricted monetary scope fail the revenue query
        # (YOUTUBE_PERMISSION or, empirically, YOUTUBE_AUTH_EXPIRED) - retry without.
        if exc.code in ("YOUTUBE_PERMISSION", "YOUTUBE_AUTH_EXPIRED") and "estimatedRevenue" in METRICS:
            resp = safe_call(
                client.reports().query,
                ids=f"channel=={channel_id}",
                startDate=start.isoformat(),
                endDate=end.isoformat(),
                metrics=METRICS.replace(",estimatedRevenue", ""),
                dimensions="day",
            )
        else:
            raise
    cols = [c["name"] for c in resp.get("columnHeaders", [])]
    out: dict[date, dict] = {}
    for row in resp.get("rows", []):
        vals = dict(zip(cols, row))
        day = vals.pop("day", None)
        if day:
            out[date.fromisoformat(str(day))] = vals
    return out


def main(days: int) -> None:
    db = SessionLocal()
    apply_overrides(db)
    end = date.today() - timedelta(days=2)      # most recent finalized day
    start = end - timedelta(days=days - 1)
    written = 0
    for ch in db.query(Channel).all():
        acc = (
            db.query(YouTubeAccount)
            .filter(YouTubeAccount.id == ch.youtube_account_id)
            .first()
        )
        if acc is None:
            logger.warning("No account for channel %s - skipped", ch.channel_id)
            continue
        try:
            aclient = get_analytics_client(db, acc)
            daily = fetch_daily(aclient, ch.channel_id, start, end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Backfill failed for %s: %s", ch.title, exc)
            continue
        n = total = 0
        for day, vals in sorted(daily.items()):
            row = (
                db.query(AnalyticsSnapshot)
                .filter_by(channel_id=ch.id, video_id=None, date=day)
                .first()
            )
            if row is None:
                row = AnalyticsSnapshot(channel_id=ch.id, video_id=None, date=day)
                db.add(row)
            row.views = int(vals.get("views", 0) or 0)
            row.watch_time_seconds = float(vals.get("estimatedMinutesWatched", 0) or 0) * 60
            row.average_view_duration_seconds = float(vals.get("averageViewDuration", 0) or 0)
            row.likes = int(vals.get("likes", 0) or 0)
            row.comments = int(vals.get("comments", 0) or 0)
            row.shares = int(vals.get("shares", 0) or 0)
            row.subscribers_gained = int(vals.get("subscribersGained", 0) or 0)
            row.subscribers_lost = int(vals.get("subscribersLost", 0) or 0)
            rev = vals.get("estimatedRevenue")
            row.estimated_revenue = float(rev) if rev is not None else None
            total += row.views
            n += 1
        db.commit()
        written += n
        logger.info("%-20s days=%3d views=%12d", ch.title, n, total)
    db.close()
    logger.info("Backfill done: %d channel-day rows written", written)


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    main(days)
