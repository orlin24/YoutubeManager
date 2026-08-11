"""Tests for the autonomous AI employee loop."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.ai_task import AiTask
from app.models.channel import Channel
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services import autonomous_service
from app.services.encryption import encrypt_str


def _seed(db, videos: list[tuple[str, int, int]]):
    user = User(id=str(uuid.uuid4()), email=f"u{uuid.uuid4().hex[:8]}@example.com", name="U", password_hash="x")
    db.add(user)
    db.flush()
    yt = f"UC{uuid.uuid4().hex[:10]}"
    acc = YouTubeAccount(id=str(uuid.uuid4()), user_id=user.id, google_account_email="g@gmail.com",
                         channel_id=yt, channel_title="Z",
                         access_token_encrypted=encrypt_str("a"), refresh_token_encrypted=encrypt_str("r"),
                         token_expiry=datetime.now(timezone.utc) + timedelta(hours=1))
    db.add(acc)
    db.flush()
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id=yt, title="Z", subscriber_count=50)
    db.add(ch)
    db.flush()
    now = datetime.now(timezone.utc)
    for i, (title, views, days_ago) in enumerate(videos):
        db.add(Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id=f"v{i}",
                     title=title, view_count=views, like_count=1, comment_count=0,
                     published_at=now - timedelta(days=days_ago)))
    db.commit()
    return ch


def _enable(db, mode="RECOMMEND_ONLY", dry_run=True, enabled=True):
    autonomous_service.set_autonomous_setting(db, "enabled", enabled)
    autonomous_service.set_autonomous_setting(db, "mode", mode)
    autonomous_service.set_autonomous_setting(db, "dry_run", dry_run)
    autonomous_service.set_autonomous_setting(db, "emergency_stop", False)


def test_cycle_disabled_by_default(db_session):
    result = autonomous_service.run_cycle(db_session)
    assert result["status"] == "off"  # default: disabled via env, mode RECOMMEND_ONLY


def test_recommend_mode_creates_tasks_but_does_not_execute(db_session):
    ch = _seed(db_session, [(f"V{i}", 50, 40 - i) for i in range(12)])  # views decline pattern
    _enable(db_session, mode="RECOMMEND_ONLY")
    result = autonomous_service.run_cycle(db_session)
    assert result["status"] in ("running", "budget_reached")
    assert result["tasks_created"] >= 0
    # no execution in RECOMMEND mode
    assert result["tasks_executed"] == 0


def test_emergency_stop_cancels_queued(db_session):
    ch = _seed(db_session, [(f"V{i}", 50, 40 - i) for i in range(12)])
    _enable(db_session, mode="SEMI_AUTO")
    db_session.add(AiTask(channel_id=ch.id, task_type="analyze", instruction="x", status="queued",
                          idempotency_key="test-1"))
    db_session.commit()
    res = autonomous_service.emergency_stop(db_session)
    assert res["status"] == "stopped"
    assert db_session.query(AiTask).filter_by(status="cancelled").count() == 1
    assert autonomous_service.run_cycle(db_session)["status"] == "emergency_stopped"


def test_idempotency_prevents_duplicates(db_session):
    ch = _seed(db_session, [(f"V{i}", 50, 40 - i) for i in range(12)])
    t1 = autonomous_service.create_task(db_session, ch.id, "analyze", "tes", idempotency_key="k-1")
    t2 = autonomous_service.create_task(db_session, ch.id, "analyze", "tes", idempotency_key="k-1")
    assert t1 is not None and t2 is None
    assert db_session.query(AiTask).filter_by(idempotency_key="k-1").count() == 1


def test_status_shape(db_session):
    _enable(db_session)
    st = autonomous_service.status(db_session)
    for k in ("status", "mode", "dry_run", "emergency_stop", "tasks_today", "waiting_approvals"):
        assert k in st
