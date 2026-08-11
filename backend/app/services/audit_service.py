"""Audit logging service - every meaningful action is recorded."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_audit(
    db: Session,
    *,
    user_id: str | None = None,
    channel_id: str | None = None,
    action: str,
    target: str | None = None,
    result: str | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        channel_id=channel_id,
        action=action,
        target=target,
        result=result,
        details=metadata,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
