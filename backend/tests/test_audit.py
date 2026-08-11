from __future__ import annotations

from app.models.audit_log import AuditLog
from app.services.audit_service import log_audit


def test_log_audit_creates_entry(db_session):
    entry = log_audit(
        db_session,
        user_id="u1",
        channel_id="c1",
        action="video_uploaded",
        target="My video",
        result="ok",
        metadata={"privacy": "private"},
    )
    assert entry.id
    assert entry.action == "video_uploaded"
    assert entry.details == {"privacy": "private"}
    assert db_session.query(AuditLog).count() == 1


def test_log_audit_without_optional_fields(db_session):
    entry = log_audit(db_session, action="user_registered")
    assert entry.action == "user_registered"
    assert entry.user_id is None
