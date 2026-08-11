"""Channel lifecycle engine.

Detects each channel's lifecycle mode (NEW/GROWTH/MONETIZED/SCALE/RECOVERY),
computes per-mode KPIs, finds winners (by views / velocity), surfaces risks
(duplicate titles, declining momentum, monetization safety), and prioritizes
actions. Everything is computed from REAL data only - never invents numbers.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.lifecycle import AiPattern, ChannelLifecycle
from app.models.video import Video
from app.utils.logging import get_logger

logger = get_logger("lifecycle")

MODES = ("NEW", "GROWTH", "MONETIZED", "SCALE", "RECOVERY")
MODE_LABELS: dict[str, str] = {
    "NEW": "Baru",
    "GROWTH": "Bertumbuh",
    "MONETIZED": "Monetisasi",
    "SCALE": "Skala",
    "RECOVERY": "Pemulihan",
}
OBJECTIVES: dict[str, str] = {
    "NEW": "Menemukan content-market fit: uji coba format dan cari apa yang ditonton.",
    "GROWTH": "Tumbuh konsisten dan memenuhi syarat monetisasi (subs + jam tonton).",
    "MONETIZED": "Memaksimalkan pendapatan berkelanjutan dari konten yang terbukti.",
    "SCALE": "Perbanyak yang sudah terbukti dan diversifikasi arus pendapatan.",
    "RECOVERY": "Diagnosa penurunan dan pulihkan performa ke tren naik.",
}

# Tunable thresholds (module level so they can be tuned in one place).
THRESHOLDS: dict[str, float] = {
    "recovery_drop_pct": 30.0,      # RECOVERY if 28d views drop >= this vs prev 28d
    "new_video_count": 10,          # NEW if fewer videos than this
    "new_lifetime_views": 2000.0,   # NEW if total views below this
    "scale_views_28d": 50000.0,     # SCALE if monetized and 28d views above this
    "scale_growth_min": -10.0,      # SCALE requires 28d growth above this
    "growth_min_subs": 100,         # GROWTH if subs >= this
    "growth_min_views_28d": 1000.0,
}


# ---- data helpers (real data only) ----------------------------------------


def _video_window(db: Session, channel_id: str, start: date, end: date) -> list[Video]:
    return (
        db.query(Video)
        .filter(Video.channel_id == channel_id, Video.published_at.isnot(None))
        .filter(
            Video.published_at >= datetime.combine(start, datetime.min.time()),
            Video.published_at <= datetime.combine(end, datetime.max.time()),
        )
        .all()
    )


def _snapshot_agg(db: Session, channel_id: str, start: date, end: date) -> dict[str, float]:
    """Aggregate channel-level analytics snapshots (video_id IS NULL) for a window."""
    rows = (
        db.query(AnalyticsSnapshot)
        .filter(
            AnalyticsSnapshot.channel_id == channel_id,
            AnalyticsSnapshot.video_id.is_(None),
            AnalyticsSnapshot.date >= start,
            AnalyticsSnapshot.date <= end,
        )
        .all()
    )
    agg: dict[str, float] = {"views": 0, "watch_time_seconds": 0, "likes": 0, "comments": 0,
                             "shares": 0, "subscribers_gained": 0, "subscribers_lost": 0}
    revenue: list[float] = []
    for r in rows:
        agg["views"] += r.views or 0
        agg["watch_time_seconds"] += r.watch_time_seconds or 0
        agg["likes"] += r.likes or 0
        agg["comments"] += r.comments or 0
        agg["shares"] += r.shares or 0
        agg["subscribers_gained"] += r.subscribers_gained or 0
        agg["subscribers_lost"] += r.subscribers_lost or 0
        if r.estimated_revenue is not None:
            revenue.append(float(r.estimated_revenue))
    if revenue:
        agg["estimated_revenue"] = sum(revenue)
    return agg


def _title_risk(videos: list[Video]) -> dict[str, Any]:
    """Duplicate / near-duplicate title detection (monetization safety + SEO)."""
    titles = [(v.title or "").strip() for v in videos if v.title]
    seen: dict[str, int] = {}
    dupes: list[str] = []
    prefix = [t[:20].lower() for t in titles]
    for i, t in enumerate(titles):
        key = t.lower()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:
            dupes.append(t)
        for j in range(i):
            if prefix[j] == prefix[i] and titles[j] != t:
                dupes.append(t)
                break
    dupes = list(dict.fromkeys(dupes))
    level = "LOW"
    reason = "Tidak ada judul duplikat yang terdeteksi."
    if len(dupes) >= 3:
        level = "HIGH"
        reason = (f"{len(dupes)} judul mirip/duplikat terdeteksi - bisa menekan jangkauan & "
                  "menimbulkan risiko hak cipta/kebijakan monetisasi.")
    elif dupes:
        level = "MEDIUM"
        reason = f"Ada judul mirip/duplikat: {dupes[0][:40]}{' dan lainnya' if len(dupes) > 1 else ''}."
    return {"level": level, "reason": reason, "duplicate_titles": dupes[:5]}


# ---- mode detection --------------------------------------------------------


def detect_channel_mode(db: Session, channel: Channel, profile: ChannelProfile | None) -> str:
    today = date.today()
    start = today - timedelta(days=27)
    prev_start = start - timedelta(days=28)
    prev_end = start - timedelta(days=1)

    all_videos = db.query(Video).filter(Video.channel_id == channel.id).all()
    total_views = sum(v.view_count or 0 for v in all_videos)
    video_count = len(all_videos)

    views28 = sum(v.view_count or 0 for v in _video_window(db, channel.id, start, today))
    views_prev = sum(v.view_count or 0 for v in _video_window(db, channel.id, prev_start, prev_end))
    subs = channel.subscriber_count or 0

    monetized = bool(profile and profile.monetized)
    revenue = _snapshot_agg(db, channel.id, start, today).get("estimated_revenue")

    if views_prev > 0 and views28 < views_prev * (1 - THRESHOLDS["recovery_drop_pct"] / 100.0) and video_count >= 5:
        return "RECOVERY"
    if video_count < THRESHOLDS["new_video_count"] or (
        video_count < 15 and total_views < THRESHOLDS["new_lifetime_views"]
    ):
        return "NEW"
    if monetized or revenue is not None:
        if views28 >= THRESHOLDS["scale_views_28d"]:
            growth = (views28 - views_prev) / views_prev * 100 if views_prev else 0.0
            if growth >= THRESHOLDS["scale_growth_min"]:
                return "SCALE"
        return "MONETIZED"
    if subs >= THRESHOLDS["growth_min_subs"] or views28 >= THRESHOLDS["growth_min_views_28d"]:
        return "GROWTH"
    return "NEW"


# ---- winners ---------------------------------------------------------------


def _as_naive(dt: datetime) -> datetime:
    """Normalize a datetime to naive-UTC for date arithmetic (sqlite stores naive)."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def detect_winners(db: Session, channel: Channel) -> list[dict[str, Any]]:
    today = _as_naive(datetime.now(timezone.utc))
    videos = _video_window(db, channel.id, today.date() - timedelta(days=365), today.date())
    videos.sort(key=lambda v: (v.view_count or 0), reverse=True)
    out: list[dict[str, Any]] = []

    def _age(v: Video) -> int:
        if not v.published_at:
            return 1
        return max((today - _as_naive(v.published_at)).days, 1)

    if videos:
        top = videos[0]
        out.append({
            "category": "VIEW WINNER",
            "title": top.title,
            "data": {"views": top.view_count, "likes": top.like_count, "comments": top.comment_count,
                     "youtube_video_id": top.youtube_video_id},
            "confidence": "HIGH",
            "note": "Video dengan views tertinggi (data nyata).",
        })
    recent = [v for v in videos if v.published_at and 0 <= _age(v) <= 28]
    if recent:
        best = max(recent, key=lambda v: (v.view_count or 0) / _age(v))
        if best.view_count and best.youtube_video_id != (videos[0].youtube_video_id if videos else None):
            out.append({
                "category": "EMERGING WINNER",
                "title": best.title,
                "data": {"views": best.view_count, "velocity": round((best.view_count or 0) / _age(best), 1),
                         "youtube_video_id": best.youtube_video_id},
                "confidence": "MEDIUM",
                "note": "Video terbaru (28 hari) dengan kecepatan views tertinggi per hari.",
            })
    if recent and len(recent) >= 3:
        low = min(recent, key=lambda v: v.view_count or 0)
        out.append({
            "category": "UNDERPERFORMER",
            "title": low.title,
            "data": {"views": low.view_count, "days_since_publish": _age(low),
                     "youtube_video_id": low.youtube_video_id},
            "confidence": "MEDIUM",
            "note": "Video terbaru dengan views terendah - evaluasi judul/thumbnail/topik.",
        })
    return out


# ---- priorities ------------------------------------------------------------


def detect_priorities(mode: str, growth_pct: float, risk: dict[str, Any],
                      winners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    if risk["level"] == "HIGH":
        priorities.append({"priority": "CRITICAL", "title": "Bereskan judul duplikat/mirip",
                           "reason": risk["reason"]})
    if mode == "RECOVERY":
        priorities.append({"priority": "HIGH", "title": "Diagnosa penyebab penurunan views",
                           "reason": f"Views 28 hari turun ({growth_pct:.0f}%) dibanding periode sebelumnya."})
    if mode == "NEW":
        priorities.append({"priority": "HIGH", "title": "Uji coba format konten secara konsisten",
                           "reason": "Channel masih mencari content-market fit."})
    if mode == "GROWTH":
        priorities.append({"priority": "HIGH", "title": "Kejar syarat monetisasi",
                           "reason": "Fokus pada watch time dan subscriber."})
    if mode in ("MONETIZED", "SCALE"):
        priorities.append({"priority": "MEDIUM", "title": "Perbanyak format yang terbukti",
                           "reason": "Eksploitasi pola pemenang yang sudah terdeteksi."})
    if winners and any(w["category"] == "VIEW WINNER" for w in winners):
        priorities.append({"priority": "MEDIUM", "title": "Buat kelanjutan dari video pemenang",
                           "reason": "Pola judul/konten pemenang terbukti menaikkan views."})
    if len(priorities) < 3:
        priorities.append({"priority": "LOW", "title": "Jaga konsistensi upload",
                           "reason": "Konsistensi adalah faktor pertumbuhan jangka panjang."})
    return priorities[:4]


# ---- orchestrator ----------------------------------------------------------


def run_channel_analysis(db: Session, channel: Channel) -> dict[str, Any]:
    profile = db.query(ChannelProfile).filter_by(channel_id=channel.id).first()
    mode = detect_channel_mode(db, channel, profile)

    today = date.today()
    start = today - timedelta(days=27)
    prev_start = start - timedelta(days=28)
    prev_end = start - timedelta(days=1)
    views28 = sum(v.view_count or 0 for v in _video_window(db, channel.id, start, today))
    views_prev = sum(v.view_count or 0 for v in _video_window(db, channel.id, prev_start, prev_end))
    growth_pct = round((views28 - views_prev) / views_prev * 100, 1) if views_prev else None
    snap = _snapshot_agg(db, channel.id, start, today)
    watch_hours = round(snap["watch_time_seconds"] / 3600.0, 1)
    subs = channel.subscriber_count or 0

    winners = detect_winners(db, channel)
    videos = db.query(Video).filter(Video.channel_id == channel.id).all()
    risk = _title_risk(videos)
    priorities = detect_priorities(mode, growth_pct or 0.0, risk, winners)

    # health score 0-100 (internal heuristic from real metrics - NOT an official YouTube metric)
    health = 50.0
    if views_prev:
        health += max(-30, min(30, growth_pct * 0.5))
    if subs >= 100:
        health += 10
    if snap["views"] > 0 and snap["likes"] + snap["comments"] > 0:
        eng = (snap["likes"] + snap["comments"]) / snap["views"] * 100
        health += min(10, eng * 2)
    if risk["level"] == "HIGH":
        health -= 15
    elif risk["level"] == "MEDIUM":
        health -= 7
    health = round(max(5, min(99, health)), 1)

    kpis: dict[str, Any] = {
        "subscribers": subs,
        "views_28d": views28,
        "growth_pct": growth_pct,
        "watch_hours_28d": watch_hours if snap["watch_time_seconds"] > 0 else None,
        "likes_28d": int(snap["likes"]),
        "comments_28d": int(snap["comments"]),
        "videos_total": len(videos),
    }
    if snap.get("estimated_revenue") is not None:
        kpis["estimated_revenue"] = round(snap["estimated_revenue"], 2)

    result = {
        "channel_id": channel.id,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "objective": OBJECTIVES.get(mode, ""),
        "health_score": health,
        "growth_pct": growth_pct,
        "kpis": kpis,
        "winners": winners,
        "risk": risk,
        "priorities": priorities,
    }
    save_lifecycle(db, channel.id, result, winners, risk)
    return result


def save_lifecycle(db: Session, channel_id: str, result: dict[str, Any],
                   winners: list[dict[str, Any]], risk: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    row = db.query(ChannelLifecycle).filter_by(channel_id=channel_id).first()
    if row is None:
        row = ChannelLifecycle(channel_id=channel_id)
        db.add(row)
    row.mode = result["mode"]
    row.objective = result["objective"]
    row.health_score = result["health_score"]
    row.growth_pct = result["growth_pct"]
    row.data = {"kpis": result["kpis"], "winners": winners, "risk": risk,
                "priorities": result["priorities"]}
    row.detected_at = now
    db.commit()

    for w in winners:
        _append_pattern(db, channel_id, "winner", w.get("title", w.get("category", "")), w)
    _append_pattern(db, channel_id, "risk", risk.get("reason", "")[:80], risk)
    for p in result["priorities"]:
        _append_pattern(db, channel_id, "recommendation", p.get("title", ""), p)
    db.commit()


def _append_pattern(db: Session, channel_id: str, pattern_type: str, title: str, data: dict) -> None:
    row = AiPattern(channel_id=channel_id, pattern_type=pattern_type,
                    title=(title or "")[:200], confidence=str(data.get("confidence", "LOW")),
                    data=data)
    db.add(row)
    ids = [r.id for r in db.query(AiPattern.id).filter_by(channel_id=channel_id)
           .order_by(AiPattern.created_at.desc()).limit(100).all()]
    if len(ids) > 60:
        stale = [i[0] for i in db.query(AiPattern.id).filter_by(channel_id=channel_id)
                 .filter(AiPattern.id.notin_(ids[:60])).all()]
        if stale:
            db.query(AiPattern).filter(AiPattern.id.in_(stale)).delete(synchronize_session=False)


def portfolio_overview(db: Session, user_channel_ids: list[str]) -> dict[str, Any]:
    if not user_channel_ids:
        return {"by_mode": {m: 0 for m in MODES}, "total": 0, "channels": [],
                "labels": MODE_LABELS, "objectives": OBJECTIVES}
    rows = db.query(ChannelLifecycle).filter(ChannelLifecycle.channel_id.in_(user_channel_ids)).all()
    by_mode: dict[str, int] = {m: 0 for m in MODES}
    channels: list[dict[str, Any]] = []
    for r in rows:
        ch = db.get(Channel, r.channel_id)
        if ch is None:
            continue
        by_mode[r.mode] = by_mode.get(r.mode, 0) + 1
        channels.append({
            "channel_id": ch.id,
            "title": ch.title,
            "mode": r.mode,
            "mode_label": MODE_LABELS.get(r.mode, r.mode),
            "health_score": r.health_score,
            "growth_pct": r.growth_pct,
            "subscribers": ch.subscriber_count,
            "views_28d": (r.data or {}).get("kpis", {}).get("views_28d"),
            "detected_at": r.detected_at,
        })
    channels.sort(key=lambda c: (c["health_score"] or 0), reverse=True)
    return {"by_mode": by_mode, "total": len(channels), "channels": channels,
            "labels": MODE_LABELS, "objectives": OBJECTIVES}
