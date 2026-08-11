"""YouTube account management: disconnect, accounts, status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.approval_request import ApprovalRequest
from app.models.audit_log import AuditLog
from app.models.ai_decision import AiDecision
from app.models.ai_task import AiTask
from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.content_plan_item import ContentPlanItem
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.security import check_csrf

router = APIRouter(prefix="/youtube", tags=["youtube"])


class DisconnectRequest(BaseModel):
    account_id: str


@router.get("/status")
def status() -> dict:
    s = get_settings()
    return {"configured": bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET)}


@router.get("/accounts")
def accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = (
        db.query(YouTubeAccount)
        .filter_by(user_id=user.id)
        .order_by(YouTubeAccount.created_at.desc())
        .all()
    )
    return {
        "items": [
            {
                "id": a.id,
                "channel_id": a.channel_id,
                "channel_title": a.channel_title,
                "channel_thumbnail": a.channel_thumbnail,
                "google_account_email": a.google_account_email,
                "connected_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in rows
        ],
        "total": len(rows),
    }


@router.post("/disconnect")
def disconnect(payload: DisconnectRequest, request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    account = db.query(YouTubeAccount).filter_by(id=payload.account_id, user_id=user.id).first()
    if account is None:
        raise AppError(404, "NOT_FOUND", "Account not found.")
    channel = db.query(Channel).filter_by(youtube_account_id=account.id).first()
    title = account.channel_title or account.channel_id
    if channel is not None:
        channel_id = channel.id
        db.query(AiDecision).filter_by(channel_id=channel_id).delete()
        db.query(AiTask).filter_by(channel_id=channel_id).delete()
        db.query(AnalyticsSnapshot).filter_by(channel_id=channel_id).delete()
        db.query(ChannelProfile).filter_by(channel_id=channel_id).delete()
        db.query(ContentPlanItem).filter_by(channel_id=channel_id).delete()
        db.query(ApprovalRequest).filter_by(channel_id=channel_id).delete()
        db.query(AuditLog).filter_by(channel_id=channel_id).delete()
        db.query(Video).filter_by(channel_id=channel_id).delete()
        db.delete(channel)
        db.commit()
    db.delete(account)
    db.commit()
    log_audit(db, user_id=user.id, action="youtube_disconnected", target=title, result="ok")
    return {"success": True}
