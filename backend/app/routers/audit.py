"""Audit log timeline."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.routers.deps import user_channel_ids

router = APIRouter(prefix="/audit", tags=["audit"])


def _audit_dict(a: AuditLog) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "channel_id": a.channel_id,
        "action": a.action,
        "target": a.target,
        "result": a.result,
        "metadata": a.details or {},
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
def list_audit(channel_id: str | None = None, limit: int = 50,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    # Channel-scoped actions + this user's account-level actions (login, credentials, settings).
    if ids:
        q = db.query(AuditLog).filter(
            or_(
                AuditLog.channel_id.in_(ids),
                and_(AuditLog.channel_id.is_(None), AuditLog.user_id == user.id),
            )
        )
    else:
        q = db.query(AuditLog).filter(AuditLog.user_id == user.id)
    if channel_id:
        q = q.filter(AuditLog.channel_id == channel_id)
    q = q.order_by(AuditLog.created_at.desc()).limit(min(limit, 200))
    entries = q.all()
    return {"items": [_audit_dict(a) for a in entries], "total": len(entries)}
