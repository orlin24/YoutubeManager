"""Tests: replied comments are hidden from the list (not deleted from YouTube)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models.channel import Channel
from app.models.replied_comment import RepliedComment
from app.models.user import User
from app.models.youtube_account import YouTubeAccount
from app.services.encryption import encrypt_str


def _seed(db) -> Channel:
    user = User(id=str(uuid.uuid4()), email="u@example.com", name="U", password_hash="x")
    db.add(user)
    db.flush()
    acc = YouTubeAccount(
        id=str(uuid.uuid4()), user_id=user.id, google_account_email="g@gmail.com",
        channel_id="UCc", channel_title="C",
        access_token_encrypted=encrypt_str("a"), refresh_token_encrypted=encrypt_str("r"),
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(acc)
    db.flush()
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id="UCc", title="C")
    db.add(ch)
    db.commit()
    return ch


def _fake_items():
    return [
        {"id": "c1", "author": "A", "text": "h", "video_id": "v1", "video_title": "t",
         "published_at": "2026-01-01T00:00:00Z", "like_count": 1},
        {"id": "c2", "author": "B", "text": "h2", "video_id": "v1", "video_title": "t",
         "published_at": "2026-01-02T00:00:00Z", "like_count": 2},
    ]


def test_list_comments_hides_replied(client, auth_headers, db_session, monkeypatch):
    from app.services.youtube_service import YouTubeService

    ch = _seed(db_session)
    db_session.add(RepliedComment(comment_id="c1", channel_id=ch.id))
    db_session.commit()

    monkeypatch.setattr("app.routers.comments.user_channel_ids", lambda db, user: [ch.id])
    monkeypatch.setattr("app.routers.comments.get_user_channel", lambda db, user, cid: ch)
    monkeypatch.setattr("app.routers.comments.get_user_account", lambda db, user, cid: MagicMock())
    monkeypatch.setattr("app.youtube.client.get_authenticated_client", lambda db, acc: MagicMock())

    def fake_get_comments(self, client, video_id=None, max_results=50, video_ids=None):
        return _fake_items()

    monkeypatch.setattr(YouTubeService, "get_comments", fake_get_comments)

    resp = client.get("/api/comments?channel_id=" + ch.id, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [i["id"] for i in body["items"]] == ["c2"]
    assert body["total"] == 1
    assert body["hidden_count"] == 1


def test_reply_marks_comment_as_replied(client, auth_headers, db_session, monkeypatch):
    ch = _seed(db_session)
    monkeypatch.setattr("app.routers.comments.get_user_account", lambda db, user, cid: MagicMock())
    monkeypatch.setattr("app.routers.comments.get_user_channel", lambda db, user, cid: ch)
    monkeypatch.setattr(
        "app.routers.comments.reply_to_comment",
        lambda db, acc, cid, text: {"id": cid, "text": text},
    )

    resp = client.post(
        "/api/comments/c1/reply?channel_id=" + ch.id,
        headers=auth_headers,
        json={"text": "Terima kasih!"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["hidden"] is True
    row = db_session.query(RepliedComment).filter_by(comment_id="c1", channel_id=ch.id).first()
    assert row is not None


def test_replied_comments_travel_with_backup(client, auth_headers, db_session):
    ch = _seed(db_session)
    db_session.add(RepliedComment(comment_id="c1", channel_id=ch.id))
    db_session.commit()
    resp = client.post("/api/backup/export", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()["tables"]["replied_comments"]
    assert any(r["comment_id"] == "c1" for r in rows)
