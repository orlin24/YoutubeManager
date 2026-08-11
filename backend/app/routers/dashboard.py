"""Dashboard: summary cards, growth, top/underperforming videos, AI recs,
pending approvals, recent actions, system health."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics.engine import compute_range, top_videos
from app.auth.deps import get_current_user
from app.database import get_db
from app.models.approval_request import ApprovalRequest
from app.models.audit_log import AuditLog
from app.models.channel import Channel
from app.models.user import User
from app.models.video import Video
from app.routers.deps import user_channel_ids
from app.routers.health import health as health_check

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(channel_id: str | None = None, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    channels = db.query(Channel).filter(Channel.id.in_(ids)).all() if ids else []

    total_videos = 0
    total_views = 0
    total_subs = 0
    total_watch = 0.0
    revenue: float | None = None

    active = None
    if channel_id and channel_id in ids:
        active = db.get(Channel, channel_id)
    elif channels:
        active = channels[0]

    if active is not None:
        stats = compute_range(db, active.id, "28d")
        overview = stats["overview"]
        total_views = overview["views"]
        total_watch = overview["watch_time_seconds"]
        revenue = overview["estimated_revenue"]
        total_videos = (
            db.query(func.count(Video.id)).filter(Video.channel_id == active.id).scalar() or 0
        )
        total_subs = active.subscriber_count

    pending = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.channel_id.in_(ids), ApprovalRequest.status == "pending")
        .order_by(ApprovalRequest.created_at.desc())
        .limit(10)
        .all()
        if ids else []
    )
    recent = (
        db.query(AuditLog)
        .filter(AuditLog.channel_id.in_(ids))
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
        if ids else []
    )
    health = health_check(db)

    data = {
        "summary": {
            "channels": len(channels),
            "videos": total_videos,
            "views": total_views,
            "subscribers": total_subs,
            "watch_time_seconds": total_watch,
            "revenue": revenue,
        },
        "growth": compute_range(db, active.id, "28d")["growth"] if active else {
            "views_delta": 0, "subscribers_delta": 0, "views_pct": None, "subscribers_pct": None,
        },
        "top_videos": top_videos(db, active.id, limit=5, worst=False) if active else [],
        "underperforming_videos": top_videos(db, active.id, limit=5, worst=True) if active else [],
        "ai_recommendations": [
            {
                "text": "Run an AI channel analysis to get recommendations.",
                "action": "analyze_channel",
            }
        ],
        "pending_approvals": [
            {
                "id": a.id,
                "action_type": a.action_type,
                "risk_level": a.risk_level,
                "reason": a.reason,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in pending
        ],
        "recent_actions": [
            {
                "id": a.id,
                "action": a.action,
                "target": a.target,
                "result": a.result,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in recent
        ],
        "system_health": health["checks"],
    }
    return data
