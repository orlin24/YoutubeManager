"""Tests for the resumable (chunked) upload flow: init -> chunks -> finalize."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

from app.models.channel import Channel
from app.models.user import User
from app.models.youtube_account import YouTubeAccount
from app.services.encryption import encrypt_str


def _seed_channel(db, user: User) -> Channel:
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


def test_chunked_upload_flow(client, auth_headers, db_session):
    user = db_session.query(User).first()
    ch = _seed_channel(db_session, user)
    data1 = b"first-chunk-"
    data2 = b"second-part"

    # init: metadata + first chunk
    resp = client.post(
        "/api/videos/upload",
        headers=auth_headers,
        data={
            "channel_id": ch.id,
            "title": "Video Uji",
            "privacy_status": "private",
            "contains_synthetic_media": "true",
            "total_bytes": str(len(data1) + len(data2)),
        },
        files={"file": ("a.mp4", io.BytesIO(data1), "video/mp4")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    upload_id = body["upload_id"]
    assert body["received_bytes"] == len(data1)

    # next chunk
    resp2 = client.post(
        "/api/videos/upload-chunk",
        headers=auth_headers,
        data={"upload_id": upload_id},
        files={"chunk": ("c.bin", io.BytesIO(data2), "application/octet-stream")},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["received_bytes"] == len(data1) + len(data2)

    # status reports received/total
    st = client.get(f"/api/videos/upload-status/{upload_id}", headers=auth_headers).json()
    assert st["received_bytes"] == len(data1) + len(data2)
    assert st["total_bytes"] == len(data1) + len(data2)
    assert "tmp_path" not in st  # internal fields never leak
    assert "thumb_data" not in st

    # finalize starts the YouTube upload thread
    fin = client.post("/api/videos/upload-finalize", headers=auth_headers, json={"upload_id": upload_id})
    assert fin.status_code == 200, fin.text
    assert fin.json()["started"] is True

    # cancel frees the session
    cancel = client.post("/api/videos/upload-cancel", headers=auth_headers, json={"upload_id": upload_id})
    assert cancel.status_code == 200


def test_chunk_unknown_upload_404(client, auth_headers):
    resp = client.post(
        "/api/videos/upload-chunk",
        headers=auth_headers,
        data={"upload_id": "tidak-ada"},
        files={"chunk": ("c.bin", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert resp.status_code == 404


def test_finalize_incomplete_upload_409(client, auth_headers, db_session):
    ch = _seed_channel(db_session, db_session.query(User).first())
    resp = client.post(
        "/api/videos/upload",
        headers=auth_headers,
        data={
            "channel_id": ch.id,
            "title": "V",
            "privacy_status": "private",
            "contains_synthetic_media": "true",
            "total_bytes": "100",  # claim 100 bytes but send only 5
        },
        files={"file": ("a.mp4", io.BytesIO(b"12345"), "video/mp4")},
    )
    upload_id = resp.json()["upload_id"]
    fin = client.post("/api/videos/upload-finalize", headers=auth_headers, json={"upload_id": upload_id})
    assert fin.status_code == 409
