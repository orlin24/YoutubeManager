"""AI CEO dashboard: overview, today's priorities, opportunities, risks,
recommendation, resource allocation, scorecard, and the Telegram CEO report.

All numbers come from REAL data; anything unavailable is N/A. Internal scores
are heuristic - never presented as official YouTube metrics.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.ai_task import AiTask
from app.models.approval_request import ApprovalRequest
from app.models.channel import Channel
from app.models.content_factory import ContentQueue
from app.models.lifecycle import ChannelLifecycle
from app.models.video import Video
from app.services.lifecycle_service import MODE_LABELS, MODES
from app.utils.logging import get_logger

logger = get_logger("ceo")


def _lcs(db: Session, ids: list[str]) -> dict[str, ChannelLifecycle]:
    if not ids:
        return {}
    return {r.channel_id: r for r in db.query(ChannelLifecycle).filter(ChannelLifecycle.channel_id.in_(ids)).all()}


def ceo_overview(db: Session, channel_ids: list[str]) -> dict[str, Any]:
    lc_map = _lcs(db, channel_ids)
    channels = db.query(Channel).filter(Channel.id.in_(channel_ids)).all() if channel_ids else []
    by_mode = {m: 0 for m in MODES}
    total_subs = 0
    total_views = 0
    revenue: float | None = 0.0
    revenue_known = False
    for ch in channels:
        lc = lc_map.get(ch.id)
        by_mode[lc.mode] = by_mode.get(lc.mode, 0) + 1
        total_subs += ch.subscriber_count or 0
        total_views += ch.view_count or 0
        if lc and (lc.data or {}).get("kpis", {}).get("estimated_revenue") is not None:
            revenue += (lc.data or {}).get("kpis", {}).get("estimated_revenue", 0)
            revenue_known = True
    produced = db.query(ContentQueue).filter(ContentQueue.channel_id.in_(channel_ids)).count() if channel_ids else 0
    published = (db.query(ContentQueue).filter(ContentQueue.channel_id.in_(channel_ids),
                                               ContentQueue.status.in_(("PUBLISHED", "ANALYZING", "COMPLETED")))
                 .count() if channel_ids else 0)
    ai_actions = (db.query(AiTask).filter(AiTask.channel_id.in_(channel_ids)).count() if channel_ids else 0)
    return {
        "total_channels": len(channels),
        "by_mode": by_mode,
        "monetized": by_mode.get("MONETIZED", 0) + by_mode.get("SCALE", 0),
        "revenue": round(revenue, 2) if revenue_known else None,
        "views": total_views,
        "subscribers": total_subs,
        "content_produced": produced,
        "content_published": published,
        "ai_actions": ai_actions,
    }


def today_priorities(db: Session, channel_ids: list[str]) -> list[dict[str, Any]]:
    """Max 5 priorities from lifecycle risks/priorities + queue + approvals."""
    lc_map = _lcs(db, channel_ids)
    items: list[dict[str, Any]] = []
    for cid, lc in lc_map.items():
        ch = db.get(Channel, cid)
        for p in (lc.data or {}).get("priorities", [])[:2]:
            items.append({"channel": ch.title if ch else cid, "priority": p.get("priority", "LOW"),
                          "title": p.get("title", ""), "reason": p.get("reason", "")})
    if channel_ids:
        waiting = (db.query(ApprovalRequest)
                   .filter(ApprovalRequest.channel_id.in_(channel_ids),
                           ApprovalRequest.status == "pending").count())
        if waiting:
            items.append({"channel": "System", "priority": "HIGH",
                          "title": f"{waiting} aksi menunggu persetujuan Anda",
                          "reason": "Tinjau di halaman Approvals."})
        queue_low = db.query(ContentQueue).filter(
            ContentQueue.channel_id.in_(channel_ids),
            ContentQueue.status.in_(("READY", "QUALITY_CHECK", "PRODUCTION", "UPLOAD_QUEUE"))).count()
        if queue_low < 3:
            items.append({"channel": "System", "priority": "MEDIUM",
                          "title": "Content queue menipis",
                          "reason": "Buat ide/brief baru untuk minggu depan."})
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    items.sort(key=lambda x: order.get(x["priority"], 9))
    return items[:5]


def opportunities(db: Session, channel_ids: list[str]) -> list[dict[str, Any]]:
    lc_map = _lcs(db, channel_ids)
    out: list[dict[str, Any]] = []
    for cid, lc in lc_map.items():
        ch = db.get(Channel, cid)
        winners = (lc.data or {}).get("winners", [])
        for w in winners:
            if w.get("category") in ("VIEW WINNER", "EMERGING WINNER"):
                out.append({"channel": ch.title if ch else cid, "type": w["category"],
                            "title": w.get("title", ""), "confidence": w.get("confidence", "LOW"),
                            "data": w.get("data", {})})
    return out[:6]


def risks(db: Session, channel_ids: list[str]) -> list[dict[str, Any]]:
    lc_map = _lcs(db, channel_ids)
    out: list[dict[str, Any]] = []
    for cid, lc in lc_map.items():
        ch = db.get(Channel, cid)
        risk = (lc.data or {}).get("risk", {})
        if risk.get("level") in ("MEDIUM", "HIGH"):
            out.append({"channel": ch.title if ch else cid, "level": risk["level"],
                        "title": risk.get("reason", "")})
    return out[:6]


def recommendation(db: Session, channel_ids: list[str]) -> dict[str, Any]:
    """Rule-based recommendation (never changes anything automatically)."""
    lc_map = _lcs(db, channel_ids)
    best: tuple[str, str, str, int] | None = None  # (channel, decision, reason, score)
    for cid, lc in lc_map.items():
        ch = db.get(Channel, cid)
        name = ch.title if ch else cid
        g = lc.growth_pct
        if lc.mode == "SCALE" and (g or 0) >= 0:
            decision, reason, score = "SCALE", f"Views tumbuh {g:.0f}% + monetized.", 90
        elif lc.mode == "RECOVERY":
            decision, reason, score = "RECOVER", "Performa menurun - fokus pemulihan.", 80
        elif lc.mode in ("MONETIZED", "GROWTH"):
            decision, reason, score = "MAINTAIN", "Stabil - pertahankan formula pemenang.", 70
        else:
            decision, reason, score = "EXPERIMENT", "Cari content-market fit (channel baru).", 60
        if best is None or score > best[3]:
            best = (name, decision, reason, score)
    if best is None:
        return {"recommendation": "N/A", "reason": "Belum ada data channel."}
    return {"channel": best[0], "decision": best[1], "reason": best[2], "confidence": "MEDIUM"}


def allocation(db: Session, channel_ids: list[str]) -> list[dict[str, Any]]:
    """Internal production allocation recommendation by channel health + mode."""
    lc_map = _lcs(db, channel_ids)
    rows: list[tuple[str, int, str]] = []
    for cid, lc in lc_map.items():
        ch = db.get(Channel, cid)
        base = {"SCALE": 40, "MONETIZED": 30, "GROWTH": 25, "RECOVERY": 15, "NEW": 10}.get(lc.mode, 10)
        if (lc.health_score or 50) < 30:
            base = min(base, 10)
        rows.append((ch.title if ch else cid, base, lc.mode))
    total = sum(r[1] for r in rows) or 1
    return [{"channel": name, "mode": mode, "share": round(share / total * 100, 1)} for name, share, mode in rows]


def scorecard(db: Session, channel_ids: list[str]) -> dict[str, Any]:
    lc_map = _lcs(db, channel_ids)
    rows = list(lc_map.values())
    if not rows:
        return {"portfolio_health": None, "growth": None, "revenue": None,
                "content_efficiency": None, "experimentation": None, "risk": None}
    health = sum(r.health_score or 0 for r in rows) / len(rows)
    growths = [r.growth_pct for r in rows if r.growth_pct is not None]
    growth = sum(growths) / len(growths) if growths else None
    revenue_known = [r for r in rows if (r.data or {}).get("kpis", {}).get("estimated_revenue") is not None]
    high_risk = sum(1 for r in rows if (r.data or {}).get("risk", {}).get("level") == "HIGH")
    # internal heuristics, clearly not official metrics
    return {
        "portfolio_health": round(min(99, max(5, health)), 1),
        "growth": round(growth, 1) if growth is not None else None,
        "revenue": round(sum((r.data or {}).get("kpis", {}).get("estimated_revenue", 0) for r in revenue_known), 2)
        if revenue_known else None,
        "content_efficiency": None,  # needs production cost data (rule #43)
        "experimentation": round(sum(1 for r in rows if (r.data or {}).get("winners")) / len(rows) * 100, 1),
        "risk": "LOW" if high_risk == 0 else ("MEDIUM" if high_risk <= 2 else "HIGH"),
    }


def telegram_ceo_report(db: Session, channel_ids: list[str]) -> str | None:
    from app.services.telegram_service import send_telegram

    ov = ceo_overview(db, channel_ids)
    prio = today_priorities(db, channel_ids)
    opp = opportunities(db, channel_ids)
    rk = risks(db, channel_ids)
    rec = recommendation(db, channel_ids)
    text = (
        "AI CEO REPORT\n\n"
        f"Channels: {ov['total_channels']}\n"
        f"Revenue: {ov['revenue'] if ov['revenue'] is not None else 'N/A'}\n"
        f"Views: {ov['views']:,}\n"
        f"Subscribers: {ov['subscribers']:,}\n"
        f"Content produced: {ov['content_produced']} | published: {ov['content_published']}\n\n"
    )
    if opp:
        o = opp[0]
        text += f"Opportunity: {o['channel']} ({o['type']})\n"
    if rk:
        r = rk[0]
        text += f"Risk: {r['channel']} ({r['level']})\n"
    text += "\nToday's Priority:\n"
    for i, p in enumerate(prio[:3], 1):
        text += f"{i}. {p['title']}\n"
    text += f"\nAI Recommendation: {rec['channel']} - {rec['decision']} ({rec['reason']})"
    if send_telegram(text[:3800]):
        logger.info("CEO report sent to Telegram")
        return text
    return None
