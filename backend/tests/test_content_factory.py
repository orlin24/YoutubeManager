"""Tests for the AI Content Factory + CEO engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.channel import Channel
from app.models.content_factory import ContentBrief, ContentIdea, ContentQueue
from app.models.lifecycle import ChannelLifecycle
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services import ceo_service, content_factory
from app.services.encryption import encrypt_str


def _seed(db, with_videos=True):
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
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id=yt, title="Z", subscriber_count=300)
    db.add(ch)
    db.flush()
    if with_videos:
        now = datetime.now(timezone.utc)
        for i in range(6):
            db.add(Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id=f"v{i}",
                         title=f"Video Lagu Populer {i}", view_count=2000 - i * 100,
                         like_count=20, comment_count=2, published_at=now - timedelta(days=i)))
    db.commit()
    return ch


def test_mix_type_spread():
    mix = {"PROVEN": 70, "VARIATION": 20, "EXPERIMENT": 10}
    assert content_factory._mix_type(mix, 0, 10) == "PROVEN"   # 70% -> 7 items
    assert content_factory._mix_type(mix, 6, 10) == "PROVEN"
    assert content_factory._mix_type(mix, 7, 10) == "VARIATION"  # +20% -> 2 items
    assert content_factory._mix_type(mix, 9, 10) == "EXPERIMENT"  # sisanya 10%


def test_duplication_check(db_session):
    ch = _seed(db_session)
    db_session.add(Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id="dup", title="Lagu Serupa Banget"))
    db_session.commit()
    high = content_factory.duplication_check(db_session, ch.id, "Lagu Serupa Banget")
    assert high["level"] == "HIGH"
    low = content_factory.duplication_check(db_session, ch.id, "Judul Sangat Berbeda Sekali")
    assert low["level"] == "LOW"


def test_quality_check_rules(db_session):
    ch = _seed(db_session)
    from app.models.content_factory import ContentBrief
    brief = ContentBrief(idea_id="x", channel_id=ch.id, title_concept="")
    db_session.add(brief)
    db_session.commit()
    result = content_factory.quality_check(db_session, brief)
    assert result["result"] == "BLOCK"  # empty title -> low score


def test_pipeline_dry_run_no_rows(db_session):
    """Dry run = simulasi OFFLINE instan: ideas terisi dari data channel, tidak menyimpan baris."""
    ch = _seed(db_session)
    result = content_factory.run_pipeline(db_session, ch, count=3, dry_run=True)
    assert result["dry_run"] is True
    assert result.get("offline") is True
    assert result["queued"] == 0
    # ide berasal dari video terpopuler di DB (tanpa LLM)
    assert len(result["ideas"]) >= 1
    assert "Lagu Populer" in result["ideas"][0]["idea"]
    assert result["ideas"][0]["quality"] in ("PASS", "WARN", "BLOCK")
    assert result["ideas"][0]["queue_id"] is None
    assert db_session.query(ContentIdea).count() == 0
    assert db_session.query(ContentBrief).count() == 0
    assert db_session.query(ContentQueue).count() == 0


def test_build_calendar(db_session):
    ch = _seed(db_session, with_videos=False)
    idea = ContentIdea(channel_id=ch.id, topic="Ide A", content_type="PROVEN", priority=8, status="IDEA")
    db_session.add(idea)
    db_session.commit()
    db_session.add(ContentQueue(channel_id=ch.id, idea_id=idea.id, title="Ide A",
                                content_type="PROVEN", status="READY", priority=8))
    db_session.commit()
    plan = content_factory.build_calendar(db_session, ch, days=7)
    assert len(plan) == 1
    assert plan[0]["title"] == "Ide A"


def test_ceo_overview_and_priorities(db_session):
    ch = _seed(db_session)
    lc = ChannelLifecycle(channel_id=ch.id, mode="GROWTH", objective="x", health_score=60,
                          growth_pct=10.0, data={"priorities": [{"priority": "HIGH", "title": "T", "reason": "R"}],
                                                 "risk": {"level": "LOW", "reason": "ok"},
                                                 "winners": [], "kpis": {}})
    db_session.add(lc)
    db_session.commit()
    ov = ceo_service.ceo_overview(db_session, [ch.id])
    assert ov["total_channels"] == 1
    prio = ceo_service.today_priorities(db_session, [ch.id])
    assert len(prio) >= 1
    rec = ceo_service.recommendation(db_session, [ch.id])
    assert rec["decision"] in ("SCALE", "RECOVER", "MAINTAIN", "EXPERIMENT")


def test_advance_queue_status(db_session):
    """advance() memajukan item satu tahap pipeline & mengisi publish_date."""
    ch = _seed(db_session)
    idea = ContentIdea(channel_id=ch.id, topic="Ide Test", angle="x", format="musik",
                       reason="r", confidence="HIGH", content_type="PROVEN", priority=8, status="IDEA")
    db_session.add(idea)
    db_session.commit()
    q = ContentQueue(channel_id=ch.id, idea_id=idea.id, title="Judul Test",
                     content_type="PROVEN", priority=8, status="QUALITY_CHECK")
    db_session.add(q)
    db_session.commit()

    from app.services import content_factory as cf
    cf.advance(db_session, q)
    assert q.status == "READY"

    cf.advance(db_session, q)
    assert q.status == "PRODUCTION"

    # maju sampai SCHEDULED -> publish_date otomatis terisi
    for _ in range(5):
        cf.advance(db_session, q)
    assert q.status == "COMPLETED"
    assert q.publish_date is not None or q.completed_at is not None


def test_advance_queue_blocks_completed(db_session):
    ch = _seed(db_session)
    q = ContentQueue(channel_id=ch.id, title="X", content_type="PROVEN", priority=5, status="COMPLETED")
    db_session.add(q)
    db_session.commit()
    from app.utils.errors import AppError
    from app.services import content_factory as cf
    try:
        cf.advance(db_session, q)
        assert False, "harusnya error"
    except AppError:
        pass
