from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.approval_service import (
    create_approval,
    register_executor,
    reject,
    approve,
)


def _make_user(db: Session) -> User:
    user = User(email="flow@example.com", name="Flow", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_approval_reject_flow(db_session):
    user = _make_user(db_session)
    approval = create_approval(
        db_session,
        channel_id="chan-1",
        action_type="delete_video",
        target_id="video-1",
        proposed_change={"title": "test"},
        reason="test reject",
        risk_level="HIGH",
        user_id=user.id,
    )
    assert approval.status == "pending"

    rejected = reject(db_session, approval.id, user.id)
    assert rejected.status == "rejected"
    assert db_session.query(AuditLog).filter_by(action="approval_rejected").count() == 1


def test_approval_approve_flow(db_session):
    user = _make_user(db_session)

    def executor(db, approval) -> dict:
        return {"executed": True, "title": (approval.proposed_change or {}).get("title")}

    register_executor("fake_action", executor)
    approval = create_approval(
        db_session,
        channel_id="chan-1",
        action_type="fake_action",
        target_id="video-1",
        proposed_change={"title": "hello"},
        reason="test approve",
        risk_level="HIGH",
        user_id=user.id,
    )
    result = approve(db_session, approval.id, user.id)
    assert result == {"executed": True, "title": "hello"}
    assert approval.status == "approved"
    assert approval.approved_at is not None
    assert db_session.query(AuditLog).filter_by(action="approval_approved").count() >= 1

    # second approve must fail
    import pytest

    from app.utils.errors import AppError

    with pytest.raises(AppError):
        approve(db_session, approval.id, user.id)
