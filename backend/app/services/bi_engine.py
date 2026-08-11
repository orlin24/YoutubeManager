"""Business Intelligence Engine.

MetricsAggregator -> BaselineEngine -> TrendEngine -> ForecastEngine ->
RiskEngine -> OpportunityEngine -> SimulationEngine -> PortfolioOptimizer ->
StrategyEngine. Statistical/time-series math in Python (NOT the LLM); the LLM
is only used for interpretation on demand. No fake predictions: everything is a
range with confidence, or INSUFFICIENT DATA. Everything is cached in a daily BI
snapshot (app_settings "bi.snapshot") so dashboards never do heavy work per
refresh. Forecasts are stored in forecast_history for accuracy tracking.
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.bi import ForecastHistory
from app.models.channel import Channel
from app.models.lifecycle import ChannelLifecycle
from app.models.video import Video
from app.utils.logging import get_logger

logger = get_logger("bi")

MODEL_VERSION = "forecast_v1"
MIN_SAMPLES = 7  # below this: INSUFFICIENT DATA
SNAPSHOT_KEY = "bi.snapshot"


# ---- statistics (pure Python, no LLM) -------------------------------------


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list[float]) -> float:
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


def _zscore_outliers(xs: list[float], z: float = 2.0) -> list[bool]:
    if len(xs) < 4:
        return [False] * len(xs)
    m, sd = _mean(xs), _stdev(xs)
    return [abs(x - m) > z * sd for x in xs] if sd > 0 else [False] * len(xs)


def _linear_trend(xs: list[float]) -> float:
    """Slope (per step) via least squares. Negative = declining."""
    n = len(xs)
    if n < 2:
        return 0.0
    idx = list(range(n))
    mx, my = (n - 1) / 2, _mean(xs)
    num = sum((i - mx) * (x - my) for i, x in zip(idx, xs))
    den = sum((i - mx) ** 2 for i in idx)
    return num / den if den else 0.0


def _exp_smoothing(values: list[float], alpha: float = 0.4) -> list[float]:
    out: list[float] = []
    s = values[0] if values else 0.0
    for v in values:
        s = alpha * v + (1 - alpha) * s
        out.append(s)
    return out


def _confidence(sample_size: int, volatility: float, consistency: float) -> float:
    """0-100 heuristic: more samples + lower volatility + stable trend -> higher."""
    if sample_size < MIN_SAMPLES:
        return 0.0
    score = 50
    score += min(25, sample_size * 1.5)
    score -= min(25, volatility * 100)
    score += min(15, consistency * 15)
    return max(10, min(90, score))


def analyze_series(values: list[float]) -> dict[str, Any]:
    """Baseline + trend + forecast for a daily metric series."""
    clean = [float(v) for v in values if v is not None]
    if len(clean) < MIN_SAMPLES:
        return {"status": "INSUFFICIENT_DATA", "sample_size": len(clean)}
    outliers = _zscore_outliers(clean)
    base = [v for v, o in zip(clean, outliers) if not o] or clean
    mean = _mean(base)
    last = clean[-1]
    prev_mean = _mean(clean[:-7]) if len(clean) > 14 else mean
    current = _mean(clean[-7:]) if len(clean) >= 7 else last
    change = (current - prev_mean) / prev_mean * 100 if prev_mean else 0.0
    slope = _linear_trend(clean)
    volatility = _stdev(clean) / mean if mean else 0.0
    if len(clean) >= 14:
        half1, half2 = _mean(clean[: len(clean) // 2]), _mean(clean[len(clean) // 2:])
        consistency = 1.0 if half2 == 0 else min(1.0, half1 / half2 if half1 <= half2 else half2 / half1)
    else:
        consistency = 1.0 - min(1.0, volatility)
    trend = "stable"
    if slope > 0 and change > 5:
        trend = "growing"
    elif slope < 0 and change < -5:
        trend = "declining"
    if volatility > 0.6:
        trend = "volatile"
    smoothed = _exp_smoothing(clean)
    horizon_scale = max(0.2, min(2.0, 1 + slope / (mean + 1e-9)))
    expected = smoothed[-1] * horizon_scale
    residual = _stdev([a - b for a, b in zip(clean, smoothed)]) if len(clean) > 2 else _stdev(clean) * 0.5
    band = max(residual * 1.5, mean * 0.1)
    confidence = _confidence(len(clean), volatility, consistency)
    return {
        "status": "OK",
        "sample_size": len(clean),
        "baseline_mean": round(mean, 2),
        "current": round(last, 2),
        "change_pct": round(change, 1),
        "trend": trend,
        "volatility": round(volatility, 3),
        "outliers": int(sum(outliers)),
        "forecast": {
            "expected": round(max(0, expected), 0),
            "lower": round(max(0, expected - band), 0),
            "upper": round(expected + band, 0),
            "confidence": round(confidence, 0),
        },
    }


# ---- MetricsAggregator ------------------------------------------------------


def _series_from_snapshots(db: Session, channel_id: str, metric: str, days: int) -> list[float]:
    """Daily metric series from AnalyticsSnapshot (channel-level rows)."""
    from app.models.analytics_snapshot import AnalyticsSnapshot

    start = date.today() - timedelta(days=days - 1)
    rows = (
        db.query(AnalyticsSnapshot)
        .filter(AnalyticsSnapshot.channel_id == channel_id,
                AnalyticsSnapshot.video_id.is_(None),
                AnalyticsSnapshot.date >= start)
        .order_by(AnalyticsSnapshot.date.asc())
        .all()
    )
    col = {"views": "views", "watch_time": "watch_time_seconds", "revenue": "estimated_revenue",
           "subscribers": "subscribers_gained"}.get(metric)
    if col is None:
        return []
    out: list[float] = []
    for r in rows:
        v = getattr(r, col, None)
        if v is not None:
            out.append(float(v))
    return out


def _video_views_by_publish_day(db: Session, channel_id: str, days: int) -> list[float]:
    """Approximation of the views trend from videos published in the window:
    one sample per upload day (its view_count), oldest -> newest. Empty days are
    skipped so the series reflects upload performance, not silent days."""
    start = datetime.now(timezone.utc) - timedelta(days=days)
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel_id, Video.published_at.isnot(None),
                Video.published_at >= start)
        .order_by(Video.published_at.asc())
        .all()
    )
    return [float(v.view_count or 0) for v in videos if (v.view_count or 0) > 0]


# ---- engines ----------------------------------------------------------------


def baseline(db: Session, channel_id: str, metric: str = "views", days: int = 28) -> dict[str, Any]:
    s = _series_from_snapshots(db, channel_id, metric, days)
    if len(s) < MIN_SAMPLES and metric == "views":
        s = _video_views_by_publish_day(db, channel_id, days)
    return analyze_series(s)


def trend(db: Session, channel_id: str, metric: str = "views", days: int = 28) -> dict[str, Any]:
    return baseline(db, channel_id, metric, days)


def forecast(db: Session, channel_id: str, metric: str, horizon_days: int = 30,
             save: bool = True) -> dict[str, Any]:
    """Views/subscribers/revenue forecast. Statistical; range + confidence."""
    s = _series_from_snapshots(db, channel_id, metric, max(horizon_days, 28))
    if len(s) < MIN_SAMPLES and metric == "views":
        s = _video_views_by_publish_day(db, channel_id, max(horizon_days, 28))
    if len(s) < MIN_SAMPLES:
        return {"metric": metric, "status": "INSUFFICIENT_DATA",
                "sample_size": len(s), "forecast": None}
    a = analyze_series(s)
    f = a["forecast"]
    if horizon_days != 30:
        # scale the 30d-ish daily forecast to the requested horizon
        factor = horizon_days / 30.0
        f = {"expected": round(f["expected"] * factor, 0),
             "lower": round(f["lower"] * factor, 0),
             "upper": round(f["upper"] * factor, 0),
             "confidence": f["confidence"]}
    if save:
        _save_forecast(db, channel_id, metric, horizon_days, f, a)
    return {"metric": metric, "status": "OK", "trend": a["trend"],
            "change_pct": a["change_pct"], "sample_size": a["sample_size"],
            "forecast": f, "model_version": MODEL_VERSION}


def _save_forecast(db: Session, channel_id: str, metric: str, horizon_days: int,
                   f: dict, a: dict) -> None:
    row = ForecastHistory(
        metric=metric,
        channel_id=channel_id,
        forecast_date=datetime.now(timezone.utc),
        target_date=datetime.now(timezone.utc) + timedelta(days=horizon_days),
        predicted_value=f["expected"],
        lower_bound=f["lower"],
        upper_bound=f["upper"],
        confidence=f["confidence"],
        model_version=MODEL_VERSION,
        sample_size=a.get("sample_size", 0),
        data_timestamp=datetime.now(timezone.utc),
        assumptions="Statistical smoothing on real analytics snapshots/videos; range, not guarantee.",
    )
    db.add(row)
    db.commit()
    # bounded history: keep the newest 200 rows per metric+channel
    ids = [r.id for r in db.query(ForecastHistory.id).filter_by(metric=metric, channel_id=channel_id)
           .order_by(ForecastHistory.forecast_date.desc()).limit(200).all()]
    stale = [i[0] for i in db.query(ForecastHistory.id).filter_by(metric=metric, channel_id=channel_id)
             .filter(ForecastHistory.id.notin_(ids)).all()]
    if stale:
        db.query(ForecastHistory).filter(ForecastHistory.id.in_(stale)).delete(synchronize_session=False)
        db.commit()


def forecast_accuracy(db: Session) -> dict[str, Any]:
    """Compare stored forecasts vs actuals when the target date has passed."""
    now = datetime.now(timezone.utc)
    rows = db.query(ForecastHistory).filter(
        ForecastHistory.target_date < now, ForecastHistory.actual_value.is_(None)).all()
    updated = 0
    for r in rows:
        actual = _current_actual(db, r.metric, r.channel_id)
        if actual is not None:
            r.actual_value = actual
            if r.predicted_value:
                r.error = round((actual - r.predicted_value) / r.predicted_value * 100, 1)
            updated += 1
    if updated:
        db.commit()
    done = db.query(ForecastHistory).filter(ForecastHistory.actual_value.isnot(None)).all()
    if not done:
        return {"status": "INSUFFICIENT_DATA", "count": 0}
    errors = [abs(r.error or 0) for r in done]
    signed = [r.error or 0 for r in done]
    mape = _mean(errors)
    bias = _mean(signed)
    return {"status": "OK", "count": len(done), "mape_pct": round(mape, 1),
            "bias_pct": round(bias, 1), "model_version": MODEL_VERSION,
            "note": "MAPE/bias internal - bukan metrik resmi."}


def _current_actual(db: Session, metric: str, channel_id: str) -> float | None:
    if metric == "views":
        ch = db.get(Channel, channel_id)
        return float(ch.view_count or 0) if ch else None
    if metric == "subscribers":
        ch = db.get(Channel, channel_id)
        return float(ch.subscriber_count or 0) if ch else None
    if metric == "revenue":
        s = _series_from_snapshots(db, channel_id, "revenue", 90)
        return sum(s) if s else None
    if metric == "watch_time":
        s = _series_from_snapshots(db, channel_id, "watch_time", 90)
        return sum(s) if s else None
    return None


# ---- RiskEngine --------------------------------------------------------------


def risk_scan(db: Session, channel: Channel, lc: ChannelLifecycle | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if lc:
        risk = (lc.data or {}).get("risk", {})
        if risk.get("level") == "HIGH":
            out.append({"category": "Content Risk", "severity": "CRITICAL",
                        "title": "Judul duplikat/mirip", "evidence": risk.get("reason", "")})
        elif risk.get("level") == "MEDIUM":
            out.append({"category": "Content Risk", "severity": "MEDIUM",
                        "title": "Judul mirip", "evidence": risk.get("reason", "")})
        if lc.mode == "RECOVERY":
            out.append({"category": "Growth Risk", "severity": "HIGH",
                        "title": "Performa menurun",
                        "evidence": f"Growth {lc.growth_pct}% (28 hari)."})
    v = baseline(db, channel.id, "views", 28)
    if v.get("status") == "OK" and v["trend"] == "declining":
        out.append({"category": "Views Risk", "severity": "MEDIUM",
                    "title": "Tren views menurun",
                    "evidence": f"Perubahan {v['change_pct']}% (28 hari)."})
    # upload consistency risk (from cadence profile)
    from app.models.channel_profile import ChannelProfile

    profile = db.query(ChannelProfile).filter_by(channel_id=channel.id).first()
    if profile and profile.upload_cadence_days:
        last = db.query(Video.published_at).filter(Video.channel_id == channel.id,
                                                   Video.published_at.isnot(None)) \
            .order_by(Video.published_at.desc()).first()
        if last and last[0]:
            days_since = (datetime.now(timezone.utc) - last[0]).days
            if days_since > profile.upload_cadence_days * 2:
                out.append({"category": "Upload Risk", "severity": "LOW",
                            "title": "Keteraturan upload menurun",
                            "evidence": f"{days_since} hari sejak video terakhir (target setiap {profile.upload_cadence_days} hari)."})
    return out


# ---- OpportunityEngine -------------------------------------------------------


def opportunity_scan(db: Session, channel: Channel, lc: ChannelLifecycle | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if lc:
        winners = (lc.data or {}).get("winners", [])
        for w in winners:
            if w.get("category") in ("VIEW WINNER", "EMERGING WINNER"):
                score = 80 if w["category"] == "VIEW WINNER" else 65
                out.append({"category": "Winning Formula", "severity": "HIGH" if score >= 75 else "MEDIUM",
                            "title": w.get("title", ""), "score": score,
                            "evidence": f"{w.get('note', '')} views {w.get('data', {}).get('views')}",
                            "action": "Buat kelanjutan/variasi formula ini."})
    return out


# ---- classification + optimization + simulation -------------------------------


def classify_channel(lc: ChannelLifecycle | None, trend_label: str) -> dict[str, str]:
    if lc is None:
        return {"class": "EXPERIMENT", "confidence": "LOW"}
    mode = lc.mode
    g = lc.growth_pct
    cls = {"SCALE": "SCALE", "MONETIZED": "MAINTAIN", "GROWTH": "GROW",
           "RECOVERY": "RECOVER", "NEW": "EXPERIMENT"}.get(mode, "MAINTAIN")
    if mode == "SCALE" and (g or 0) < -10:
        cls = "MAINTAIN"
    if mode == "GROWTH" and trend_label == "declining":
        cls = "RECOVER"
    return {"class": cls, "confidence": "MEDIUM"}


def simulate(scenario: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What-if simulation using historical elasticity. MODEL ESTIMATE, not certainty."""
    uploads_now = float(state.get("uploads_per_week", 1) or 1)
    uploads_new = float(scenario.get("uploads_per_week", uploads_now) or uploads_now)
    views_per_upload = float(state.get("views_per_upload", 0) or 0)
    change_uploads = (uploads_new - uploads_now) / uploads_now if uploads_now else 0.0
    elastic = min(1.2, max(0.2, float(scenario.get("elasticity", 0.6))))
    effect = change_uploads * elastic
    capacity_delta = float(scenario.get("capacity_shift_pct", 0) or 0) / 100.0
    effect += capacity_delta * 0.5
    best = (1 + max(effect, 0) * 1.3) if effect > 0 else (1 + effect * 0.8)
    worst = 1 + min(effect, 0) * 0.8 if effect < 0 else 1 + effect * 0.3
    base = 1 + effect
    conf = max(25, min(75, 60 - abs(effect) * 40))
    return {
        "scenario_name": scenario.get("name", "Simulasi"),
        "model_estimate": True,
        "best_case": {"views_delta_pct": round((best - 1) * 100, 1)},
        "base_case": {"views_delta_pct": round((base - 1) * 100, 1)},
        "worst_case": {"views_delta_pct": round((worst - 1) * 100, 1)},
        "production_load_delta_pct": round(change_uploads * 100, 1),
        "risk": "MEDIUM" if abs(effect) > 0.3 else "LOW",
        "confidence": round(conf, 0),
        "assumptions": f"Elastisitas {elastic}; views/upload {views_per_upload:.0f}; MODEL ESTIMATE - bukan jaminan.",
    }


def optimize(db: Session, channel_ids: list[str], constraints: dict[str, Any]) -> dict[str, Any]:
    """Allocate production capacity by opportunity/health, honoring constraints."""
    lc_map = {r.channel_id: r for r in
              db.query(ChannelLifecycle).filter(ChannelLifecycle.channel_id.in_(channel_ids)).all()} if channel_ids else {}
    rows: list[dict[str, Any]] = []
    for cid in channel_ids:
        ch = db.get(Channel, cid)
        lc = lc_map.get(cid)
        base = {"SCALE": 40, "MONETIZED": 30, "GROWTH": 25, "RECOVERY": 15, "NEW": 10}.get(lc.mode if lc else "NEW", 10)
        if lc and (lc.health_score or 50) < 30:
            base = min(base, 10)
        rows.append({"channel_id": cid, "title": ch.title if ch else cid, "score": base,
                     "mode": lc.mode if lc else "NEW"})
    total = sum(r["score"] for r in rows) or 1
    max_videos = float(constraints.get("max_videos_per_day", 4) or 4)
    for r in rows:
        r["share"] = round(r["score"] / total * 100, 1)
        r["videos_per_week"] = max(1, round(max_videos * 7 * r["share"] / 100))
    return {"items": rows, "constraints": constraints, "note": "Rekomendasi internal, MODEL ESTIMATE."}


# ---- snapshot / cache ---------------------------------------------------------


def compute_snapshot(db: Session) -> dict[str, Any]:
    """Build the daily BI snapshot (scheduler job). Cached; dashboards read cache."""
    from app.services.lifecycle_service import MODE_LABELS

    channels = db.query(Channel).all()
    lcs = {r.channel_id: r for r in db.query(ChannelLifecycle).all()}
    per_channel: list[dict[str, Any]] = []
    all_risks: list[dict[str, Any]] = []
    all_opps: list[dict[str, Any]] = []
    for ch in channels:
        lc = lcs.get(ch.id)
        v = baseline(db, ch.id, "views", 28)
        f_views = forecast(db, ch.id, "views", 30, save=True)
        f_subs = forecast(db, ch.id, "subscribers", 30, save=True)
        f_rev = forecast(db, ch.id, "revenue", 30, save=False)
        risks = risk_scan(db, ch, lc)
        opps = opportunity_scan(db, ch, lc)
        all_risks += risks
        all_opps += opps
        cls = classify_channel(lc, v.get("trend", "stable"))
        per_channel.append({
            "channel_id": ch.id,
            "title": ch.title,
            "mode": lc.mode if lc else "NEW",
            "mode_label": MODE_LABELS.get(lc.mode, lc.mode) if lc else "Baru",
            "class": cls["class"],
            "views_forecast": f_views,
            "subs_forecast": f_subs,
            "revenue_forecast": f_rev,
            "risk": risks,
            "opportunities": opps,
        })
    allocation = optimize(db, [c.id for c in channels], {"max_videos_per_day": 4})
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "per_channel": per_channel,
        "risks": all_risks,
        "opportunities": all_opps,
        "allocation": allocation,
    }
    _cache_snapshot(db, snapshot)
    return snapshot


def _cache_snapshot(db: Session, snapshot: dict) -> None:
    from app.models.app_setting import AppSetting

    row = db.query(AppSetting).filter_by(key=SNAPSHOT_KEY).first()
    if row is None:
        row = AppSetting(key=SNAPSHOT_KEY, value={})
        db.add(row)
    row.value = snapshot
    db.commit()


def get_snapshot(db: Session, force: bool = False) -> dict[str, Any]:
    from app.models.app_setting import AppSetting

    if not force:
        row = db.query(AppSetting).filter_by(key=SNAPSHOT_KEY).first()
        if row and isinstance(row.value, dict) and row.value.get("per_channel"):
            return row.value
    return compute_snapshot(db)


def strategic_answers(db: Session) -> list[dict[str, str]]:
    """Evidence-first answers to the 7 CEO questions."""
    snap = get_snapshot(db)
    channels = snap.get("per_channel", [])
    growing = [c["title"] for c in channels if c.get("class") == "GROW"]
    declining = [c["title"] for c in channels if c.get("class") in ("RECOVER",)]
    risk = snap.get("risks", [])
    opp = snap.get("opportunities", [])
    answers = [
        {"question": "How is the business doing?",
         "answer": f"{len(channels)} channel terpantau. "
                   f"Risiko tinggi: {sum(1 for r in risk if r.get('severity') == 'CRITICAL')}, "
                   f"peluang: {len(opp)}."},
        {"question": "What is growing?",
         "answer": ", ".join(growing) if growing else "Belum ada channel berstatus GROW."},
        {"question": "What is declining?",
         "answer": ", ".join(declining) if declining else "Tidak ada channel berstatus RECOVER."},
        {"question": "What should I do today?",
         "answer": "; ".join((r.get("title", "") for r in sorted(risk, key=lambda x: x.get("severity", ""))[:2]))
         if risk else "Tidak ada risiko kritis hari ini."},
        {"question": "Where is the biggest opportunity?",
         "answer": opp[0]["title"] if opp else "Belum ada peluang terdeteksi."},
        {"question": "Where is the biggest risk?",
         "answer": risk[0]["title"] if risk else "Tidak ada risiko tinggi."},
        {"question": "What is likely to happen next?",
         "answer": _next_outlook(channels)},
    ]
    return answers


def _next_outlook(channels: list[dict[str, Any]]) -> str:
    parts = []
    for c in channels[:3]:
        f = c.get("views_forecast", {})
        if f.get("status") == "OK" and f.get("forecast"):
            parts.append(f"{c['title']}: {f['trend']}, expected {f['forecast']['expected']:.0f} views (30 hari).")
    return " ".join(parts) if parts else "Data belum cukup untuk outlook (INSUFFICIENT DATA)."


def morning_report(db: Session) -> str | None:
    """AI CEO MORNING REPORT -> Telegram (deduplicated: once per day)."""
    from app.services.telegram_service import send_telegram

    snap = get_snapshot(db)
    answers = strategic_answers(db)
    risks = snap.get("risks", [])
    opps = snap.get("opportunities", [])
    channels = snap.get("per_channel", [])
    growing = [c["title"] for c in channels if c.get("class") == "GROW"]
    declining = [c["title"] for c in channels if c.get("class") == "RECOVER"]
    text = (
        "AI CEO MORNING REPORT\n"
        "------------------------------\n\n"
        f"Portfolio: {len(channels)} channel\n"
        f"Growing: {len(growing)} | Stable: {len(channels) - len(growing) - len(declining)} | Declining: {len(declining)}\n\n"
    )
    if opps:
        o = opps[0]
        text += f"TOP OPPORTUNITY\n{o.get('title', '')} ({o.get('severity', '')})\n\n"
    if risks:
        r = risks[0]
        text += f"TOP RISK\n{r.get('title', '')} ({r.get('severity', '')})\n\n"
    text += "TODAY'S PRIORITY\n"
    for a in answers[3:5]:
        text += f"- {a['answer']}\n"
    text += "\nOUTLOOK\n" + (answers[6]["answer"] if len(answers) > 6 else "INSUFFICIENT DATA")
    if send_telegram(text[:3800]):
        logger.info("AI CEO morning report sent")
        return text
    return None
