"""Regression tests for bugs found in the full-system QA pass."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.channel import Channel
from app.models.content_factory import ContentIdea
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services import content_factory
from app.services.encryption import encrypt_str


def _seed(db):
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
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id=yt, title="Z", subscriber_count=100)
    db.add(ch)
    db.flush()
    now = datetime.now(timezone.utc)
    for i in range(6):
        db.add(Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id=f"v{i}",
                     title=f"Lagu Populer {i}", view_count=1500, like_count=10, comment_count=1,
                     published_at=now - timedelta(days=i)))
    db.commit()
    return ch


def test_generate_ideas_no_name_error(db_session, monkeypatch):
    """BUG: 'load_system_prompt' was not defined - every Content Factory
    generation crashed with NameError. Regression: ideas generate + save."""
    ch = _seed(db_session)

    class _Idea:
        topic = "Ide A"; angle = "x"; format = "musik"; target_audience = "ibu-ibu"; reason = "karena pola A"; confidence = "HIGH"

    class _Ideas:
        ideas = [_Idea(), _Idea(), _Idea()]

    def fake_llm(db, cid, component, system, user, model_cls):
        return {"ideas": [{"topic": "Ide A", "angle": "x", "format": "musik",
                           "target_audience": "ibu", "reason": "karena pola A", "confidence": "HIGH"},
                          {"topic": "Ide B", "angle": "y", "format": "musik",
                           "target_audience": "ibu", "reason": "karena pola B", "confidence": "MEDIUM"},
                          {"topic": "Ide C", "angle": "z", "format": "musik",
                           "target_audience": "ibu", "reason": "karena pola C", "confidence": "LOW"}]}

    monkeypatch.setattr(content_factory, "_llm", fake_llm)
    ideas = content_factory.generate_ideas(db_session, ch, count=3)
    assert len(ideas) == 3
    assert db_session.query(ContentIdea).count() == 3
    # mix 70/20/10 over 3 items -> PROVEN, PROVEN, VARIATION
    types = [i["content_type"] for i in ideas]
    assert types == ["PROVEN", "PROVEN", "VARIATION"]


def test_autonomous_cycle_is_coroutine():
    """BUG: scheduler passed the async cycle to asyncio.to_thread -> coroutine
    never awaited -> the autonomous worker never ran. Regression: it stays a
    coroutine function the loop awaits directly."""
    import inspect

    from app.tasks import scheduler

    assert inspect.iscoroutinefunction(scheduler._run_autonomous_cycle)
    # and the loop must await it, not to_thread it
    src = inspect.getsource(scheduler.scheduler_loop)
    assert "await _run_autonomous_cycle()" in src
    assert "to_thread(_run_autonomous_cycle)" not in src


def test_content_factory_pipeline_dry_run_imports_ok():
    """The pipeline entry point imports cleanly (no NameError at call time)."""
    assert hasattr(content_factory, "load_system_prompt")
