"""Tests for the Telegram upload-reminder logic."""
from __future__ import annotations

from datetime import date, timedelta

from app.tasks.scheduler import _cadence_label, _should_remind


def test_not_due_when_on_schedule():
    today = date(2026, 8, 10)
    assert _should_remind(3, today - timedelta(days=2), None, today) is False


def test_due_when_overdue_and_never_reminded():
    today = date(2026, 8, 10)
    assert _should_remind(3, today - timedelta(days=4), None, today) is True


def test_due_when_overdue_and_reminder_window_elapsed():
    today = date(2026, 8, 10)
    # reminded 4 days ago, cadence 3 -> window (3 days) already passed -> remind again
    assert _should_remind(3, today - timedelta(days=9), today - timedelta(days=4), today) is True


def test_no_reminder_inside_window():
    today = date(2026, 8, 10)
    # reminded yesterday -> still inside the 3-day window -> skip
    assert _should_remind(3, today - timedelta(days=4), today - timedelta(days=1), today) is False


def test_no_cadence_or_no_upload_never_reminds():
    today = date(2026, 8, 10)
    assert _should_remind(0, today - timedelta(days=9), None, today) is False
    assert _should_remind(3, None, None, today) is False


def test_cadence_label():
    assert _cadence_label(1) == "1 hari"
    assert _cadence_label(3) == "3 hari"
    assert _cadence_label(7) == "1 minggu"
    assert _cadence_label(14) == "14 hari"


def test_profile_api_saves_cadence(client, auth_headers, db_session):
    """The profile PATCH endpoint persists upload_cadence_days end to end."""
    import uuid
    from datetime import datetime, timedelta, timezone

    from app.models.channel import Channel
    from app.models.channel_profile import ChannelProfile
    from app.models.user import User
    from app.models.youtube_account import YouTubeAccount
    from app.services.encryption import encrypt_str

    user = db_session.query(User).first()
    acc = YouTubeAccount(
        id=str(uuid.uuid4()), user_id=user.id, google_account_email="g@gmail.com",
        channel_id="UCr", channel_title="R",
        access_token_encrypted=encrypt_str("a"), refresh_token_encrypted=encrypt_str("r"),
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(acc)
    db_session.flush()
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id="UCr", title="R")
    db_session.add(ch)
    db_session.flush()
    db_session.add(ChannelProfile(channel_id=ch.id))
    db_session.commit()

    resp = client.patch(
        f"/api/channels/{ch.id}/profile",
        headers=auth_headers,
        json={"upload_cadence_days": 3, "upload_frequency": "3 hari sekali"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["upload_cadence_days"] == 3

    # reload from DB: persisted
    p = db_session.query(ChannelProfile).filter_by(channel_id=ch.id).first()
    assert p.upload_cadence_days == 3
