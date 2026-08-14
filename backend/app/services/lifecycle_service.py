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
from app.services import risk_engine
from app.services.confidence_engine import confidence_payload, level_from_score, level_human
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
    """Repetitive-content risk via risk_engine (audit #1).

    Similar titles are REPETITIVE_CONTENT_RISK, never COPYRIGHT_RISK or
    MONETIZATION_RISK without evidence, and never CRITICAL for similarity alone.
    """
    risk = risk_engine.assess_repetitive_content(list(videos))
    # keep a backward-compatible "level" derived from the new severity
    level = risk["severity"] if risk["severity"] not in ("INSUFFICIENT_DATA",) else "LOW"
    return {
        "level": level,
        "reason": risk["reason"],
        "duplicate_titles": risk["evidence"],
        "category": risk["category"],
        "category_label": risk["category_label"],
        "risk_score": risk["risk_score"],
        "severity": risk["severity"],
        "confidence": risk["confidence"],
        "sample_size": risk["sample_size"],
        "recommended_action": risk["recommended_action"],
    }


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


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    return float(vals[mid]) if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def _pattern_count(v: Video, videos: list[Video]) -> int:
    """How many videos in `videos` share the 20-char title prefix of `v`."""
    prefix = (v.title or "").strip().lower()[:20]
    if not prefix:
        return 1
    return sum(1 for x in videos if (x.title or "").strip().lower().startswith(prefix))


def detect_winners(db: Session, channel: Channel) -> list[dict[str, Any]]:
    """Baseline-aware winner detection (audit #7, #8).

    Every winner is compared against the channel baseline (median/mean views)
    and carries a `pattern_status`: PROVEN (10+ videos share the pattern and
    outperform baseline), PROMISING (3+ videos), OUTLIER (a single viral video
    - NOT a proven pattern), INCONCLUSIVE (no clear pattern). The channel trend
    is NOT mixed with content momentum here (audit #6).
    """
    today = _as_naive(datetime.now(timezone.utc))
    videos = _video_window(db, channel.id, today.date() - timedelta(days=365), today.date())
    videos.sort(key=lambda v: (v.view_count or 0), reverse=True)
    out: list[dict[str, Any]] = []

    values = [float(v.view_count or 0) for v in videos]
    n = len(values)
    median = _median(values)
    mean = sum(values) / n if n else 0.0

    def _age(v: Video) -> int:
        if not v.published_at:
            return 1
        return max((today - _as_naive(v.published_at)).days, 1)

    def _baseline(views: float) -> dict[str, Any]:
        return {
            "median": round(median, 1),
            "mean": round(mean, 1),
            "sample_size": n,
            "ratio_vs_median": round(views / median, 1) if median else None,
        }

    if videos:
        top = videos[0]
        top_views = top.view_count or 0
        pc = _pattern_count(top, videos)
        if n >= 10 and median and top_views >= median * 2:
            pattern_status, confidence = "PROVEN", "HIGH"
            note = f"Pola berulang ({pc} video mirip) konsisten outperform baseline {top_views / median:.1f}x median channel."
        elif pc >= 3 and median and top_views >= median * 1.5:
            pattern_status, confidence = "PROMISING", "MEDIUM"
            note = f"Pola mulai terlihat ({pc} video dengan pola mirip) dengan performa {top_views / median:.1f}x median."
        elif median and top_views >= median * 1.5:
            pattern_status, confidence = "OUTLIER", "LOW"
            note = "Satu video unggul (outlier) - belum membuktikan pola berulang; jangan jadikan patokan strategi."
        else:
            pattern_status, confidence = "INCONCLUSIVE", "LOW"
            note = "Video dengan views tertinggi, tapi belum ada pola yang jelas."
        out.append({
            "category": "VIEW WINNER",
            "pattern_status": pattern_status,
            "title": top.title,
            "data": {"views": top.view_count, "likes": top.like_count, "comments": top.comment_count,
                     "youtube_video_id": top.youtube_video_id},
            "confidence": confidence,
            "note": note,
            "baseline": _baseline(top_views),
        })
    recent = [v for v in videos if v.published_at and 0 <= _age(v) <= 28]
    if recent:
        best = max(recent, key=lambda v: (v.view_count or 0) / _age(v))
        if best.view_count and best.youtube_video_id != (videos[0].youtube_video_id if videos else None):
            pc = _pattern_count(best, videos)
            status = "PROMISING" if pc >= 3 else "OUTLIER" if median and (best.view_count or 0) >= median * 1.5 else "INCONCLUSIVE"
            out.append({
                "category": "EMERGING WINNER",
                "pattern_status": status,
                "title": best.title,
                "data": {"views": best.view_count, "velocity": round((best.view_count or 0) / _age(best), 1),
                         "youtube_video_id": best.youtube_video_id},
                "confidence": "MEDIUM" if status == "PROMISING" else "LOW",
                "note": "Video terbaru (28 hari) dengan kecepatan views tertinggi per hari.",
                "baseline": _baseline(best.view_count or 0),
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
            "baseline": _baseline(low.view_count or 0),
        })

    # metric-specific winners (audit #7) - only with a real sample behind them
    if n >= 5:
        ctrs = [v.ctr for v in videos if v.ctr]
        if ctrs:
            med_ctr = _median(ctrs)
            cw = max(videos, key=lambda v: v.ctr or 0)
            if cw.ctr and med_ctr and cw.ctr >= med_ctr * 2:
                out.append({
                    "category": "CTR_WINNER", "title": cw.title, "confidence": "MEDIUM",
                    "note": f"CTR {cw.ctr:.1f}% vs median channel {med_ctr:.1f}% - thumbnail/judul sangat menarik.",
                    "data": {"ctr": cw.ctr, "views": cw.view_count, "youtube_video_id": cw.youtube_video_id},
                })
        rets = [(v, (v.average_view_duration_seconds or 0) / (v.duration_seconds or 1)) for v in videos
                if v.average_view_duration_seconds and v.duration_seconds]
        if len(rets) >= 5:
            med_ret = _median([r for _, r in rets])
            best_v, best_r = max(rets, key=lambda x: x[1])
            if best_r >= med_ret * 1.3 and best_r >= 0.4:
                out.append({
                    "category": "RETENTION_WINNER", "title": best_v.title, "confidence": "MEDIUM",
                    "note": f"Retensi {(best_r * 100):.0f}% durasi video vs median channel {(med_ret * 100):.0f}% - konten ditonton sampai akhir.",
                    "data": {"retention_ratio": round(best_r, 2), "youtube_video_id": best_v.youtube_video_id},
                })
    return out


# ---- priorities ------------------------------------------------------------


def detect_priorities(mode: str, growth_pct: float, risk: dict[str, Any],
                      winners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evidence-first priorities (audit #13, #14, #15).

    Each item gets an internal priority_score = Impact + Confidence + Urgency +
    Evidence - Effort, then CRITICAL/HIGH counts are normalized (max 1 CRITICAL,
    max 3 HIGH) and the top 5 are returned. A similar-title risk can no longer
    become CRITICAL on its own (that needs an actual CRITICAL risk); a views
    decline is HIGH at most.
    """
    conf_val = {"HIGH": 80, "MEDIUM": 55, "LOW": 25, "INSUFFICIENT_DATA": 10}
    items: list[dict[str, Any]] = []
    sev = risk.get("severity") or risk.get("level") or "LOW"
    if sev in ("CRITICAL", "HIGH"):
        items.append({
            "priority": sev if sev == "CRITICAL" else "HIGH",
            "title": "Bereskan pola judul repetitif" if risk.get("category") == "REPETITIVE_CONTENT_RISK" else "Tangani risiko konten",
            "reason": risk.get("reason", ""),
            "confidence": risk.get("confidence", "LOW"),
            "evidence": risk.get("evidence", ""),
            "sample_size": risk.get("sample_size", 0),
            "impact": 90 if sev == "CRITICAL" else 70,
            "urgency": 85 if sev == "CRITICAL" else 60,
            "effort": 45,
        })
    if mode == "RECOVERY" and growth_pct is not None:
        items.append({"priority": "HIGH", "title": "Diagnosa penyebab penurunan views",
                      "reason": f"Views 28 hari turun ({growth_pct:.0f}%) dibanding periode sebelumnya.",
                      "confidence": "MEDIUM", "evidence": f"Growth {growth_pct:+.1f}%",
                      "sample_size": 2, "impact": 70, "urgency": 70, "effort": 40})
    if mode == "NEW":
        items.append({"priority": "HIGH", "title": "Uji coba format konten secara konsisten",
                      "reason": "Channel masih mencari content-market fit.",
                      "confidence": "MEDIUM", "evidence": "Belum ada pola pemenang",
                      "sample_size": 0, "impact": 65, "urgency": 65, "effort": 45})
    if mode == "GROWTH":
        items.append({"priority": "HIGH", "title": "Kejar syarat monetisasi",
                      "reason": "Fokus pada watch time dan subscriber.",
                      "confidence": "MEDIUM", "evidence": "Mode pertumbuhan terdeteksi",
                      "sample_size": 0, "impact": 70, "urgency": 55, "effort": 40})
    if mode in ("MONETIZED", "SCALE"):
        items.append({"priority": "MEDIUM", "title": "Perbanyak format yang terbukti",
                      "reason": "Eksploitasi pola pemenang yang sudah terdeteksi.",
                      "confidence": "MEDIUM", "evidence": "Mode stabil/monetisasi",
                      "sample_size": 0, "impact": 55, "urgency": 40, "effort": 40})
    # only PROVEN/PROMISING patterns drive a "buat kelanjutan" priority (audit #21)
    proven = [w for w in winners
              if w.get("category") == "VIEW WINNER" and w.get("pattern_status") in ("PROVEN", "PROMISING")]
    if proven:
        w = proven[0]
        items.append({"priority": "MEDIUM", "title": "Buat kelanjutan pola pemenang",
                      "reason": w.get("note", "Pola pemenang terdeteksi dari data aktual."),
                      "confidence": w.get("confidence", "MEDIUM"),
                      "evidence": w.get("note", ""),
                      "sample_size": (w.get("baseline") or {}).get("sample_size", 0),
                      "impact": 55, "urgency": 45, "effort": 50})
    if len(items) < 3:
        items.append({"priority": "LOW", "title": "Jaga konsistensi upload",
                      "reason": "Konsistensi adalah faktor pertumbuhan jangka panjang.",
                      "confidence": "MEDIUM", "evidence": "Best practice konsistensi konten",
                      "sample_size": 0, "impact": 35, "urgency": 30, "effort": 20})

    for it in items:
        impact = it.pop("impact", 50)
        urgency = it.pop("urgency", 50)
        effort = it.pop("effort", 40)
        confidence = conf_val.get(it.get("confidence", "LOW"), 30)
        evidence = min(80, 10 + (it.get("sample_size") or 0) * 5)
        it["priority_score"] = risk_engine.priority_score(impact, confidence, urgency, evidence, effort)

    items = risk_engine.normalize_priorities(items, max_critical=1, max_high=3)
    return items[:5]


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

    # preliminary health BEFORE risks, so the performance risk can use it
    raw_health = 50.0
    if views_prev:
        raw_health += max(-30, min(30, growth_pct * 0.5))
    if subs >= 100:
        raw_health += 10
    if snap["views"] > 0 and snap["likes"] + snap["comments"] > 0:
        eng = (snap["likes"] + snap["comments"]) / snap["views"] * 100
        raw_health += min(10, eng * 2)

    # full risk list (audit #2): every category is assessed, evidence-first
    risks: list[dict[str, Any]] = [risk]
    risks.append(risk_engine.assess_performance_decline(growth_pct, raw_health))
    risks.append(risk_engine.copyright_assessment(sample_size=len(videos)))
    risks.append(risk_engine.monetization_assessment(sample_size=len(videos)))
    risks.append(risk_engine.policy_assessment())
    if profile:
        last_upload = max((v for v in videos if v.published_at), key=lambda v: v.published_at, default=None)
        last_days = (date.today() - _as_naive(last_upload.published_at).date()).days if last_upload else None
        risks.append(risk_engine.assess_upload_consistency(profile.upload_cadence_days, last_days))
    priorities = detect_priorities(mode, growth_pct or 0.0, risk, winners)

    # health score 0-100 (internal heuristic from real metrics - NOT an official YouTube metric)
    health = raw_health
    # health reflects every assessed risk by severity (not just title risk)
    _sev_deduction = {"CRITICAL": 15, "HIGH": 10, "MEDIUM": 5, "LOW": 2}
    for r in risks:
        if r.get("risk_score") is not None:
            health -= _sev_deduction.get(r.get("severity"), 0)
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
        "risks": risks,
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
                "risks": result.get("risks", [risk]), "priorities": result["priorities"]}
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
