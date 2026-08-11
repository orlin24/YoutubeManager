"""Tests for the backup/restore feature (single-file full data backup)."""
from __future__ import annotations

import uuid

from app.models.channel import Channel
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services.encryption import decrypt_str, encrypt_str


def _seed(user: User, db) -> YouTubeAccount:
    acc = YouTubeAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        google_account_email="owner@gmail.com",
        channel_id="UC_test_channel",
        channel_title="Test Channel",
        access_token_encrypted=encrypt_str("ACCESS_TOKEN_ABC"),
        refresh_token_encrypted=encrypt_str("REFRESH_TOKEN_XYZ"),
    )
    db.add(acc)
    db.flush()
    ch = Channel(
        id=str(uuid.uuid4()),
        youtube_account_id=acc.id,
        channel_id="UC_test_channel",
        title="Test Channel",
        subscriber_count=123,
    )
    db.add(ch)
    db.flush()
    db.add(
        Video(
            id=str(uuid.uuid4()),
            channel_id=ch.id,
            youtube_video_id="abc123",
            title="Video A",
            view_count=42,
        )
    )
    db.commit()
    return acc


def test_backup_export_contains_plaintext_tokens(client, auth_headers, db_session):
    user = db_session.query(User).first()
    assert user is not None
    _seed(user, db_session)

    resp = client.post("/api/backup/export", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["app"] == "ai-youtube-manager"
    assert payload["format_version"] == 1
    assert payload["tables"]["channels"][0]["title"] == "Test Channel"
    assert payload["tables"]["videos"][0]["youtube_video_id"] == "abc123"
    # OAuth tokens are exported in plaintext so they can be re-encrypted elsewhere
    acc_row = payload["tables"]["youtube_accounts"][0]
    assert acc_row["access_token_encrypted"] == "ACCESS_TOKEN_ABC"
    assert acc_row["refresh_token_encrypted"] == "REFRESH_TOKEN_XYZ"
    assert "Content-Disposition" in resp.headers


def test_backup_restore_round_trip(client, auth_headers, db_session):
    user = db_session.query(User).first()
    acc = _seed(user, db_session)
    exported = client.post("/api/backup/export", headers=auth_headers)
    assert exported.status_code == 200

    # wipe local data, then restore from the file
    db_session.query(Video).delete()
    db_session.query(Channel).delete()
    db_session.query(YouTubeAccount).delete()
    db_session.commit()
    assert db_session.query(YouTubeAccount).count() == 0

    resp = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("backup.json", exported.content, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["restored"]["youtube_accounts"] == 1

    restored = db_session.query(YouTubeAccount).filter_by(id=acc.id).first()
    assert restored is not None
    assert restored.channel_title == "Test Channel"
    # tokens were re-encrypted with the current server key
    assert decrypt_str(restored.access_token_encrypted) == "ACCESS_TOKEN_ABC"
    assert decrypt_str(restored.refresh_token_encrypted) == "REFRESH_TOKEN_XYZ"
    assert db_session.query(Channel).count() == 1
    assert db_session.query(Video).count() == 1


def test_backup_password_protected(client, auth_headers, db_session):
    _seed(db_session.query(User).first(), db_session)

    exported = client.post(
        "/api/backup/export", headers=auth_headers, json={"password": "rahasia"}
    )
    assert exported.status_code == 200
    body = exported.content
    assert body.lstrip()[:1] != b"{"  # encrypted, not plain JSON

    # no password -> 400
    r = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("b.enc", body, "application/octet-stream")},
    )
    assert r.status_code == 400

    # wrong password -> 400
    r = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("b.enc", body, "application/octet-stream")},
        data={"password": "salah"},
    )
    assert r.status_code == 400

    # correct password -> 200
    r = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("b.enc", body, "application/octet-stream")},
        data={"password": "rahasia"},
    )
    assert r.status_code == 200, r.text
    assert db_session.query(YouTubeAccount).count() == 1


def test_backup_restore_replaces_existing_data(client, auth_headers, db_session):
    user = db_session.query(User).first()
    _seed(user, db_session)
    exported = client.post("/api/backup/export", headers=auth_headers)
    assert exported.status_code == 200

    # add an extra row after the export - it must disappear after restore
    extra = YouTubeAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        channel_id="UC_extra",
        channel_title="Extra",
        access_token_encrypted=encrypt_str("X"),
        refresh_token_encrypted=encrypt_str("Y"),
    )
    db_session.add(extra)
    db_session.commit()
    assert db_session.query(YouTubeAccount).count() == 2

    resp = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("backup.json", exported.content, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    assert db_session.query(YouTubeAccount).count() == 1
    assert db_session.query(YouTubeAccount).filter_by(channel_id="UC_extra").count() == 0


def test_backup_rejects_invalid_file(client, auth_headers):
    resp = client.post(
        "/api/backup/restore",
        headers=auth_headers,
        files={"file": ("junk.bin", b"not a backup at all", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "backup" in resp.json()["error"]["message"].lower()
