"""Approval system: create/reject/approve requests for HIGH-RISK actions.

HIGH-RISK actions never execute directly. They create an approval_request; the
action itself runs only after a human approves it, via the EXECUTORS registry.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models.approval_request import ApprovalRequest
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.logging import get_logger

logger = get_logger("approval")

# action_type -> callable(db, approval) -> dict (executes the approved action)
EXECUTORS: dict[str, Callable[[Session, ApprovalRequest], dict]] = {}


def register_executor(action_type: str, fn: Callable[[Session, ApprovalRequest], dict]) -> None:
    EXECUTORS[action_type] = fn


def create_approval(
    db: Session,
    *,
    channel_id: str,
    action_type: str,
    target_id: str | None = None,
    proposed_change: dict,
    reason: str,
    risk_level: str = "HIGH",
    user_id: str | None = None,
) -> ApprovalRequest:
    approval = ApprovalRequest(
        channel_id=channel_id,
        action_type=action_type,
        target_id=target_id,
        proposed_change=proposed_change or {},
        reason=reason,
        risk_level=risk_level,
        status="pending",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    log_audit(
        db,
        user_id=user_id,
        channel_id=channel_id,
        action="approval_requested",
        target=action_type,
        result="pending",
        metadata={"approval_id": approval.id, "proposed_change": proposed_change},
    )
    return approval


def _resolve(db: Session, approval_id: str) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise AppError(404, "NOT_FOUND", "Approval request not found.")
    if approval.status != "pending":
        raise AppError(409, "ALREADY_RESOLVED", "This approval request was already resolved.")
    return approval


def reject(db: Session, approval_id: str, user_id: str | None = None) -> ApprovalRequest:
    approval = _resolve(db, approval_id)
    approval.status = "rejected"
    approval.resolved_by_user_id = user_id
    db.commit()
    db.refresh(approval)
    log_audit(
        db,
        user_id=user_id,
        channel_id=approval.channel_id,
        action="approval_rejected",
        target=approval.action_type,
        result="rejected",
        metadata={"approval_id": approval.id},
    )
    return approval


def approve(db: Session, approval_id: str, user_id: str | None = None) -> dict:
    approval = _resolve(db, approval_id)
    result: dict = {}
    executor = EXECUTORS.get(approval.action_type)
    if executor is not None:
        try:
            result = executor(db, approval) or {}
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Approval executor failed", exc_info=exc)
            raise AppError(500, "APPROVAL_EXECUTION_FAILED", "The action could not be executed.") from exc
    approval.status = "approved"
    approval.approved_at = datetime.now(timezone.utc)
    approval.resolved_by_user_id = user_id
    db.commit()
    db.refresh(approval)
    log_audit(
        db,
        user_id=user_id,
        channel_id=approval.channel_id,
        action="approval_approved",
        target=approval.action_type,
        result="approved",
        metadata={"approval_id": approval.id, "execution_result": result},
    )
    return result
