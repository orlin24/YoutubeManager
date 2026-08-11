"""Tests for the OAuth/comment fixes: force-ssl scope, per-video comment
fetching, and auth_error marking on refresh failure."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.youtube_account import YouTubeAccount
from app.services.encryption import encrypt_str
from app.services.oauth import SCOPES
from app.services.youtube_service import YouTubeService
from app.utils.errors import AppError


def test_get_videos_uses_playlist_items_not_search():
    """Listing videos must use playlistItems (1 quota unit), never search (100)."""
    from app.services.youtube_service import YouTubeService

    svc = YouTubeService()
    used: dict = {}

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def execute(self):
            return self._payload

    class FakeClient:
        def playlistItems(self):
            class P:
                def list(self, **kw):
                    used["playlistId"] = kw.get("playlistId")
                    return FakeResp(
                        {
                            "items": [
                                {"contentDetails": {"videoId": "v1"}},
                                {"contentDetails": {"videoId": "v2"}},
                            ]
                        }
                    )

            return P()

        def videos(self):
            class V:
                def list(self, **kw):
                    used["video_ids"] = kw["id"]
                    return FakeResp(
                        {
                            "items": [
                                {
                                    "id": "v1",
                                    "snippet": {"title": "A", "publishedAt": "2026-01-01T00:00:00Z"},
                                    "contentDetails": {"duration": "PT2M"},
                                    "statistics": {"viewCount": "10", "likeCount": "1", "commentCount": "0"},
                                    "status": {"privacyStatus": "public"},
                                }
                            ]
                        }
                    )

            return V()

    out = svc.get_videos(FakeClient(), "UCabc123", max_results=50)
    assert out and out[0]["youtube_video_id"] == "v1"
    assert used["playlistId"] == "UUabc123"  # uploads playlist
    assert used["video_ids"] == "v1,v2"


def test_traffic_sources_parses_rows():
    from app.services.youtube_service import YouTubeService

    svc = YouTubeService()

    class FakeResp:
        def execute(self):
            return {
                "rows": [["RELATED_VIDEO", "800"], ["YT_SEARCH", "200"], ["EXT_URL", "0"]],
                "columnHeaders": [{"name": "insightTrafficSourceType"}, {"name": "views"}],
            }

    class FakeThreads:
        def query(self, **kw):
            assert kw["dimensions"] == "insightTrafficSourceType"
            assert kw["metrics"] == "views"
            return FakeResp()

    class FakeClient:
        def reports(self):
            return FakeThreads()

    out = svc.get_traffic_sources(FakeClient(), "UCx", days=28)
    assert len(out) == 3
    assert out[0]["label"] == "Rekomendasi video"
    assert out[0]["views"] == 800
    assert out[0]["percent"] == 80.0
    assert out[1]["label"] == "Pencarian YouTube"
    assert out[1]["percent"] == 20.0
    # source without views still listed with 0% and its label
    assert out[2]["label"] == "Situs luar"
    assert out[2]["views"] == 0


def test_scopes_include_force_ssl():
    """commentThreads/list requires youtube.force-ssl for OAuth; without it every
    comment call fails with 403 'insufficient authentication scopes'."""
    assert "https://www.googleapis.com/auth/youtube.force-ssl" in SCOPES


def test_get_comments_per_video_fetches_each_video():
    svc = YouTubeService()
    client = MagicMock()

    def side_effect(**kw):
        vid = kw["videoId"]
        req = MagicMock()
        req.execute.return_value = {
            "items": [
                {
                    "id": f"t-{vid}",
                    "snippet": {
                        "videoId": vid,
                        "topLevelComment": {
                            "snippet": {
                                "authorDisplayName": "Penonton",
                                "textOriginal": "Keren!",
                                "likeCount": 3,
                                "publishedAt": "2026-01-01T00:00:00Z",
                            }
                        },
                    },
                }
            ]
        }
        return req

    client.commentThreads().list.side_effect = side_effect
    out = svc.get_comments(client, video_ids=["v1", "v2"], max_results=10)
    assert len(out) == 2
    assert {c["video_id"] for c in out} == {"v1", "v2"}
    assert out[0]["author"] == "Penonton"
    assert out[0]["text"] == "Keren!"
    # each video requested with videoId
    assert client.commentThreads().list.call_count == 2


def test_get_comments_skips_broken_videos():
    from googleapiclient.errors import HttpError

    svc = YouTubeService()
    client = MagicMock()

    def side_effect(**kw):
        if kw["videoId"] == "broken":
            resp = type("R", (), {"status": 404, "reason": "Not Found"})()
            body = b'{"error":{"errors":[{"reason":"notFound"}]}}'
            raise HttpError(resp, body, "uri")
        req = MagicMock()
        req.execute.return_value = {"items": []}
        return req

    client.commentThreads().list.side_effect = side_effect
    out = svc.get_comments(client, video_ids=["broken", "ok"], max_results=10)
    assert out == []


def test_refresh_failure_marks_auth_error(db_session, monkeypatch):
    from app.youtube import client as yt_client

    acc = YouTubeAccount(
        id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        channel_id="UCx",
        channel_title="X",
        access_token_encrypted=encrypt_str("old"),
        refresh_token_encrypted=encrypt_str("refresh"),
        token_expiry=datetime(2020, 1, 1, tzinfo=timezone.utc),  # expired -> must refresh
    )
    db_session.add(acc)
    db_session.commit()

    def boom(self, req):
        raise Exception("invalid_grant")

    monkeypatch.setattr("google.oauth2.credentials.Credentials.refresh", boom)
    with pytest.raises(AppError):
        yt_client._build_credentials(db_session, acc)
    db_session.refresh(acc)
    assert acc.auth_error
    assert "Connect ulang" in acc.auth_error


def test_recent_comments_prefers_videos_with_comments(db_session, monkeypatch):
    """Comment fetch must target videos that actually have comments (comment_count),
    not merely the newest videos (which often have zero comments)."""
    from datetime import datetime, timedelta

    from app.ai import memory
    from app.models.channel import Channel
    from app.models.user import User
    from app.models.video import Video

    user = User(id=str(uuid.uuid4()), email="u@example.com", name="U", password_hash="x")
    db_session.add(user)
    acc = YouTubeAccount(
        id=str(uuid.uuid4()), user_id=user.id, google_account_email="g@gmail.com",
        channel_id="UCc", channel_title="C", access_token_encrypted=encrypt_str("a"),
        refresh_token_encrypted=encrypt_str("r"), token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(acc)
    db_session.flush()
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id="UCc", title="C")
    db_session.add(ch)
    db_session.flush()
    base = datetime.now(timezone.utc)
    db_session.add_all([
        Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id="new0", title="baru 0 komentar", comment_count=0, published_at=base),
        Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id="new1", title="baru 0 komentar", comment_count=0, published_at=base - timedelta(hours=1)),
        Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id="rich", title="banyak komentar", comment_count=42, published_at=base - timedelta(days=30)),
    ])
    db_session.commit()

    captured: dict = {}

    def fake_client(*a, **kw):
        captured["client"] = True
        return object()

    def fake_get_comments(self, client, video_id=None, max_results=50, video_ids=None):
        captured["video_ids"] = video_ids
        return [{"id": "x", "author": "A", "text": "h", "video_id": "rich"}]

    from app.services.youtube_service import YouTubeService
    from app.youtube import client as yt_client

    monkeypatch.setattr(yt_client, "get_authenticated_client", fake_client)
    monkeypatch.setattr(YouTubeService, "get_comments", fake_get_comments)
    out = memory.get_recent_comments(db_session, ch, limit=10)
    assert captured["video_ids"] == ["rich"]  # only the comment-rich video is targeted
    assert len(out) == 1


def test_refresh_with_naive_expiry_is_normalized(db_session, monkeypatch):
    from google.oauth2.credentials import Credentials

    from app.youtube import client as yt_client

    acc = YouTubeAccount(
        id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        channel_id="UCn",
        channel_title="N",
        access_token_encrypted=encrypt_str("old"),
        refresh_token_encrypted=encrypt_str("refresh"),
        token_expiry=datetime(2020, 1, 1),  # legacy naive value
    )
    db_session.add(acc)
    db_session.commit()

    def ok(self, req):
        self.token = "fresh"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", ok)
    creds = yt_client._build_credentials(db_session, acc)
    assert creds.token == "fresh"  # refresh fired despite naive stored expiry
    db_session.refresh(acc)
    assert acc.auth_error is None


def test_refresh_success_clears_auth_error(db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from google.oauth2.credentials import Credentials

    from app.youtube import client as yt_client

    acc = YouTubeAccount(
        id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        channel_id="UCy",
        channel_title="Y",
        access_token_encrypted=encrypt_str("old"),
        refresh_token_encrypted=encrypt_str("refresh"),
        token_expiry=datetime(2020, 1, 1, tzinfo=timezone.utc),  # expired -> must refresh
        auth_error="Gagal memperbarui token Google",
    )
    db_session.add(acc)
    db_session.commit()

    def ok(self, req):
        self.token = "new-access"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", ok)
    creds = yt_client._build_credentials(db_session, acc)
    db_session.refresh(acc)
    assert creds.token == "new-access"
    assert acc.auth_error is None
    assert acc.token_expiry is not None
