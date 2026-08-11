"""Lifecycle & portfolio endpoints: channel mode, winners, patterns, priorities."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.channel import Channel
from app.models.lifecycle import AiPattern, ChannelLifecycle
from app.models.user import User
from app.routers.deps import get_user_channel, user_channel_ids
from app.services.audit_service import log_audit
from app.services.lifecycle_service import MODE_LABELS, OBJECTIVES, portfolio_overview, run_channel_analysis
from app.utils.security import check_csrf

router = APIRouter(tags=["lifecycle"])


@router.get("/channels/{channel_id}/lifecycle")
def channel_lifecycle(channel_id: str, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)) -> dict:
    """Latest lifecycle snapshot for a channel (mode, KPIs, winners, priorities)."""
    get_user_channel(db, user, channel_id)
    row = db.query(ChannelLifecycle).filter_by(channel_id=channel_id).first()
    if row is None:
        return {"detected": False, "message": "Belum ada analisis lifecycle. Jalankan Analisis AI terlebih dahulu."}
    return {
        "detected": True,
        "channel_id": channel_id,
        "mode": row.mode,
        "mode_label": MODE_LABELS.get(row.mode, row.mode),
        "objective": row.objective or OBJECTIVES.get(row.mode, ""),
        "health_score": row.health_score,
        "growth_pct": row.growth_pct,
        "detected_at": row.detected_at,
        **(row.data or {}),
    }


@router.post("/channels/{channel_id}/analyze")
def analyze_channel_lifecycle(channel_id: str, request: Request,
                              user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)) -> dict:
    """Run lifecycle detection + winner/risk/priority analysis and save it."""
    check_csrf(request)
    ch = get_user_channel(db, user, channel_id)
    result = run_channel_analysis(db, ch)
    log_audit(db, user_id=user.id, channel_id=ch.id, action="lifecycle_analyzed",
              target=ch.title, result="ok", metadata={"mode": result["mode"]})
    return result


@router.get("/channels/{channel_id}/patterns")
def channel_patterns(channel_id: str, pattern_type: str = "",
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    """AI pattern memory for a channel (winners, formulas, risks, recommendations)."""
    get_user_channel(db, user, channel_id)
    q = db.query(AiPattern).filter(AiPattern.channel_id == channel_id)
    if pattern_type:
        q = q.filter(AiPattern.pattern_type == pattern_type)
    rows = q.order_by(AiPattern.created_at.desc()).limit(50).all()
    return {"items": [
        {"pattern_type": r.pattern_type, "title": r.title, "confidence": r.confidence,
         "data": r.data, "created_at": r.created_at}
        for r in rows
    ]}


@router.get("/portfolio/overview")
def portfolio(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Portfolio: lifecycle mode counts + per-channel comparison table."""
    ids = user_channel_ids(db, user)
    return portfolio_overview(db, ids)


@router.get("/portfolio/priorities")
def portfolio_priorities(user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> dict:
    """All channels' AI priorities sorted by criticality, for the day's focus."""
    ids = user_channel_ids(db, user)
    items: list[dict] = []
    if ids:
        rows = db.query(ChannelLifecycle).filter(ChannelLifecycle.channel_id.in_(ids)).all()
        for r in rows:
            ch = db.get(Channel, r.channel_id)
            for p in (r.data or {}).get("priorities", []):
                items.append({
                    "channel_id": r.channel_id,
                    "channel_title": ch.title if ch else r.channel_id,
                    "mode": r.mode,
                    "priority": p.get("priority", "LOW"),
                    "title": p.get("title", ""),
                    "reason": p.get("reason", ""),
                })
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    items.sort(key=lambda x: order.get(x["priority"], 9))
    return {"items": items}
