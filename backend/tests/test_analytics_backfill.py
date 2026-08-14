"""Analytics snapshot upsert + backfill helpers (regression for Pi empty charts)."""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.channel import Channel
from app.models.user import User
from app.models.youtube_account import YouTubeAccount
from app.services import youtube_service
from app.services.encryption import encrypt_str
from scripts.backfill_analytics import fetch_daily


def _make_channel(db, name="Ch"):
    user = User(id=str(uuid4()), email=f"u{uuid4().hex[:8]}@x.com", name="U", password_hash="x")
    db.add(user)
    db.flush()
    acc = YouTubeAccount(
        id=str(uuid4()), user_id=user.id, google_account_email="g@g.com",
        channel_id=f"UC{uuid4().hex[:10]}", channel_title=name,
        access_token_encrypted=encrypt_str("a"), refresh_token_encrypted=encrypt_str("r"),
        token_expiry=None,
    )
    db.add(acc)
    db.flush()
    ch = Channel(id=str(uuid4()), youtube_account_id=acc.id, channel_id=acc.channel_id, title=name)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def test_upsert_writes_to_given_day(db_session):
    ch = _make_channel(db_session)
    day = date.today() - timedelta(days=2)
    youtube_service._upsert_channel_snapshot(db_session, ch, {"views": 123, "likes": 4}, day)
    db_session.commit()
    rows = db_session.query(AnalyticsSnapshot).filter_by(channel_id=ch.id, video_id=None).all()
    assert len(rows) == 1
    assert rows[0].date == day
    assert rows[0].views == 123
    # upsert lagi (sync berikutnya) -> tidak duplikat
    youtube_service._upsert_channel_snapshot(db_session, ch, {"views": 150, "likes": 5}, day)
    db_session.commit()
    assert db_session.query(AnalyticsSnapshot).filter_by(channel_id=ch.id, video_id=None).count() == 1


def test_upsert_skips_when_no_data(db_session):
    """Never fabricate: tanpa data final (API masih lag), jangan tulis baris 0."""
    ch = _make_channel(db_session)
    youtube_service._upsert_channel_snapshot(db_session, ch, None)
    youtube_service._upsert_channel_snapshot(db_session, ch, {})
    assert db_session.query(AnalyticsSnapshot).filter_by(channel_id=ch.id).count() == 0


def test_backfill_fetch_daily_parses_rows_and_retries_without_revenue():
    class FakeResp:
        def __init__(self, rows):
            self._rows = rows
            self.headers = {"content-type": "application/json"}

        def execute(self):
            return self

        def get(self, key, default=None):
            return {"rows": self._rows,
                    "columnHeaders": [{"name": "day"}, {"name": "views"}]}.get(key, default)

    from app.youtube.client import AppError

    class FakeClient:
        """Stub for youtubeAnalytics client: client.reports().query(**kwargs)."""

        def __init__(self, handler):
            self.calls: list[dict] = []
            self._handler = handler

        def reports(self):
            return self

        def query(self, **kwargs):
            self.calls.append(kwargs)
            return self._handler(kwargs)

    def handler(kwargs):
        if "estimatedRevenue" in kwargs.get("metrics", ""):
            raise AppError(401, "YOUTUBE_AUTH_EXPIRED", "no monetary scope")
        return FakeResp([["2026-08-10", 10], ["2026-08-11", 20]])

    q = FakeClient(handler)
    out = fetch_daily(q, "UCx", date(2026, 8, 1), date(2026, 8, 13))
    assert len(out) == 2
    assert out[date(2026, 8, 10)]["views"] == 10
    # retry terjadi tanpa estimatedRevenue
    assert any("estimatedRevenue" not in c.get("metrics", "") for c in q.calls)
