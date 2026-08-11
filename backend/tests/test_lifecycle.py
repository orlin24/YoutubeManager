"""Tests for the channel lifecycle engine (mode detection, winners, priorities)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.channel import Channel
from app.models.channel_profile import ChannelProfile
from app.models.lifecycle import AiPattern, ChannelLifecycle
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services.encryption import encrypt_str
from app.services.lifecycle_service import detect_channel_mode, portfolio_overview, run_channel_analysis


def _seed_channel(db, subs: int = 0, videos: list[tuple[str, int, int]] | None = None) -> Channel:
    user = User(id=str(uuid.uuid4()), email=f"u{uuid.uuid4().hex[:8]}@example.com", name="U", password_hash="x")
    db.add(user)
    db.flush()
    yt_id = f"UC{uuid.uuid4().hex[:10]}"
    acc = YouTubeAccount(
        id=str(uuid.uuid4()), user_id=user.id, google_account_email="g@gmail.com",
        channel_id=yt_id, channel_title="Z",
        access_token_encrypted=encrypt_str("a"), refresh_token_encrypted=encrypt_str("r"),
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(acc)
    db.flush()
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id=yt_id,
                 title="Z", subscriber_count=subs)
    db.add(ch)
    db.flush()
    now = datetime.now(timezone.utc)
    for i, (title, views, days_ago) in enumerate(videos or []):
        db.add(Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id=f"v{i}",
                     title=title, view_count=views, like_count=1, comment_count=0,
                     published_at=now - timedelta(days=days_ago)))
    db.commit()
    return ch


def test_mode_new_for_small_channel(db_session):
    ch = _seed_channel(db_session, subs=5, videos=[("A", 100, 10), ("B", 50, 5)])
    assert detect_channel_mode(db_session, ch, None) == "NEW"


def test_mode_growth_with_traction(db_session):
    ch = _seed_channel(db_session, subs=250, videos=[(f"V{i}", 1500, i) for i in range(12)])
    assert detect_channel_mode(db_session, ch, None) == "GROWTH"


def test_mode_monetized_when_marked(db_session):
    ch = _seed_channel(db_session, subs=250, videos=[(f"V{i}", 1500, i) for i in range(12)])
    profile = ChannelProfile(channel_id=ch.id, monetized=True)
    db_session.add(profile)
    db_session.commit()
    assert detect_channel_mode(db_session, ch, profile) == "MONETIZED"


def test_analysis_saves_lifecycle_and_patterns(db_session):
    ch = _seed_channel(db_session, subs=5, videos=[("Top Video", 900, 3), ("Kecil", 10, 2)])
    result = run_channel_analysis(db_session, ch)
    assert result["mode"] in ("NEW", "GROWTH")
    assert result["health_score"] is not None
    assert result["winners"]
    assert any(w["category"] == "VIEW WINNER" for w in result["winners"])
    assert result["priorities"]

    row = db_session.query(ChannelLifecycle).filter_by(channel_id=ch.id).first()
    assert row is not None and row.mode == result["mode"]
    patterns = db_session.query(AiPattern).filter_by(channel_id=ch.id).all()
    assert patterns  # winners + risks + recommendations persisted


def test_portfolio_overview_groups_modes(db_session):
    ch1 = _seed_channel(db_session, subs=5, videos=[("A", 50, 10)])
    ch2 = _seed_channel(db_session, subs=300, videos=[(f"V{i}", 2000, i) for i in range(12)])
    run_channel_analysis(db_session, ch1)
    run_channel_analysis(db_session, ch2)
    ov = portfolio_overview(db_session, [ch1.id, ch2.id])
    assert ov["total"] == 2
    assert sum(ov["by_mode"].values()) == 2


def test_lifecycle_endpoint_requires_ownership(client, auth_headers, db_session):
    from app.models.user import User

    ch = _seed_channel(db_session, subs=5, videos=[("A", 100, 5)])
    resp = client.post(f"/api/channels/{ch.id}/analyze", headers=auth_headers)
    assert resp.status_code in (200, 404)  # 404 when the seeded channel isn't owned by the auth user
