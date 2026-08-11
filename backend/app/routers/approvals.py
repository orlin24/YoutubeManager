"""Approval requests: list, detail, approve, reject."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.approval_request import ApprovalRequest
from app.models.user import User
from app.routers.deps import user_channel_ids
from app.services.approval_service import approve as approve_service
from app.services.approval_service import reject as reject_service
from app.utils.errors import AppError
from app.utils.security import check_csrf

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _approval_dict(a: ApprovalRequest) -> dict:
    return {
        "id": a.id,
        "channel_id": a.channel_id,
        "action_type": a.action_type,
        "target_id": a.target_id,
        "proposed_change": a.proposed_change or {},
        "reason": a.reason,
        "risk_level": a.risk_level,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "approved_at": a.approved_at.isoformat() if a.approved_at else None,
    }


@router.get("")
def list_approvals(status: str = "", channel_id: str | None = None,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    q = db.query(ApprovalRequest).filter(ApprovalRequest.channel_id.in_(ids)) if ids else db.query(ApprovalRequest).filter(False)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    if channel_id:
        q = q.filter(ApprovalRequest.channel_id == channel_id)
    q = q.order_by(ApprovalRequest.created_at.desc()).limit(200)
    approvals = q.all()
    return {"items": [_approval_dict(a) for a in approvals], "total": len(approvals)}


@router.get("/{approval_id}")
def get_approval(approval_id: str, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None or approval.channel_id not in ids:
        raise AppError(404, "NOT_FOUND", "Approval request not found.")
    return _approval_dict(approval)


@router.post("/{approval_id}/approve")
def approve(approval_id: str, request: Request, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ids = user_channel_ids(db, user)
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None or approval.channel_id not in ids:
        raise AppError(404, "NOT_FOUND", "Approval request not found.")
    result = approve_service(db, approval_id, user.id)
    return {"success": True, "result": result, "approval": _approval_dict(approval)}


@router.post("/{approval_id}/reject")
def reject(approval_id: str, request: Request, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ids = user_channel_ids(db, user)
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None or approval.channel_id not in ids:
        raise AppError(404, "NOT_FOUND", "Approval request not found.")
    result = reject_service(db, approval_id, user.id)
    return {"success": True, "approval": _approval_dict(result)}
