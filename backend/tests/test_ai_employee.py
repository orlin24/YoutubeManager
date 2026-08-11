"""Tests for the 'AI as employee' features: autonomous daily report, AI comment
reply draft, action execution (READ immediate, HIGH_RISK via approval), Telegram."""
from __future__ import annotations

import uuid

import pytest

from app.ai.service import generate_comment_reply, run_daily_report
from app.models.ai_task import AiTask
from app.models.approval_request import ApprovalRequest
from app.models.channel import Channel
from app.models.user import User
from app.models.youtube_account import YouTubeAccount


def _user(db) -> User:
    u = User(id=str(uuid.uuid4()), email="u@example.com", name="U", password_hash="x")
    db.add(u)
    db.commit()
    return u


def _seed_channel(db, user: User) -> Channel:
    acc = YouTubeAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        google_account_email="x@gmail.com",
        channel_id="UCx",
        channel_title="X Channel",
        access_token_encrypted="enc",
        refresh_token_encrypted="ref",
    )
    db.add(acc)
    db.flush()
    ch = Channel(id=str(uuid.uuid4()), youtube_account_id=acc.id, channel_id="UCx", title="X Channel")
    db.add(ch)
    db.commit()
    return ch


# ---- autonomous daily report ---------------------------------------------


def test_run_daily_report_completes_queued_task_when_ai_disabled(db_session):
    ch = _seed_channel(db_session, _user(db_session))
    task = AiTask(channel_id=ch.id, task_type="daily_report", status="queued",
                  instruction="Produce today's channel report.")
    db_session.add(task)
    db_session.commit()

    result = run_daily_report(db_session, ch, task)
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.completed_at is not None
    assert "AI disabled" in result["summary"]
    assert result["task_id"] == task.id


# ---- AI comment reply draft ----------------------------------------------


def test_generate_comment_reply_fallback(db_session):
    ch = _seed_channel(db_session, _user(db_session))
    draft = generate_comment_reply(db_session, ch, "Keren banget videonya!", "Budi")
    assert draft.strip()
    assert "Budi" in draft or "Terima kasih" in draft


def test_ai_draft_endpoint(client, auth_headers, db_session):
    user = db_session.query(User).first()
    ch = _seed_channel(db_session, user)
    resp = client.post(
        "/api/comments/ai-draft",
        headers=auth_headers,
        json={"channel_id": ch.id, "comment_text": "Mantap videonya!", "author": "Budi"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["draft"].strip()


# ---- action execution ------------------------------------------------------


def test_execute_read_action_runs_immediately(client, auth_headers, db_session):
    user = db_session.query(User).first()
    ch = _seed_channel(db_session, user)
    resp = client.post(
        "/api/ai/actions/execute",
        headers=auth_headers,
        json={"channel_id": ch.id, "action_id": "get_channel_info", "params": {}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approved"] is True
    assert body["result"] is not None


def test_execute_high_risk_creates_approval(client, auth_headers, db_session):
    user = db_session.query(User).first()
    ch = _seed_channel(db_session, user)
    resp = client.post(
        "/api/ai/actions/execute",
        headers=auth_headers,
        json={"channel_id": ch.id, "action_id": "reply_comment",
              "params": {"comment_id": "c1", "text": "Terima kasih!"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["approved"] is False
    appr = db_session.query(ApprovalRequest).filter_by(id=body["approval_id"]).first()
    assert appr is not None
    assert appr.status == "pending"
    assert appr.action_type == "reply_comment"


def test_execute_unknown_tool_404(client, auth_headers, db_session):
    user = db_session.query(User).first()
    ch = _seed_channel(db_session, user)
    resp = client.post(
        "/api/ai/actions/execute",
        headers=auth_headers,
        json={"channel_id": ch.id, "action_id": "does_not_exist", "params": {}},
    )
    assert resp.status_code == 404


# ---- Telegram -------------------------------------------------------------


def test_telegram_not_configured_returns_false():
    from app.services.telegram_service import send_telegram

    assert send_telegram("halo") is False


def test_telegram_send_ok(monkeypatch):
    import app.services.telegram_service as ts

    class FakeSettings:
        TELEGRAM_BOT_TOKEN = "123:ABC"
        TELEGRAM_CHAT_ID = "456"

    monkeypatch.setattr(ts, "get_settings", lambda: FakeSettings())

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True}

    captured: dict = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["json"] = kw["json"]
        return FakeResp()

    monkeypatch.setattr(ts.httpx, "post", fake_post)
    assert ts.send_telegram("laporan harian") is True
    assert "123:ABC" in captured["url"]
    assert captured["json"]["chat_id"] == "456"
    assert captured["json"]["text"].startswith("laporan harian")


def test_telegram_send_fails(monkeypatch):
    import app.services.telegram_service as ts

    class FakeSettings:
        TELEGRAM_BOT_TOKEN = "123:ABC"
        TELEGRAM_CHAT_ID = "456"

    monkeypatch.setattr(ts, "get_settings", lambda: FakeSettings())

    class FakeResp:
        status_code = 400

        def json(self):
            return {"ok": False}

    monkeypatch.setattr(ts.httpx, "post", lambda *a, **kw: FakeResp())
    assert ts.send_telegram("x") is False


def test_telegram_credentials_save(client, auth_headers):
    resp = client.patch(
        "/api/settings/credentials/telegram",
        headers=auth_headers,
        json={"bot_token": "111:AAA", "chat_id": "222"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True


# ---- content pattern recommendations -------------------------------------


def test_content_patterns_endpoint(client, auth_headers, db_session, monkeypatch):
    from app.ai import service as ai_service

    ch = _seed_channel(db_session, db_session.query(User).first())
    canned = {
        "analysis": "Pola terbukti: judul dengan nama artis + kata kunci genre.",
        "recommendations": [
            {"title": "T1", "description": "D1", "target_keyword": "musik", "reason": "karena X"},
            {"title": "T2", "description": "D2", "target_keyword": "", "reason": "karena Y"},
            {"title": "T3", "description": "D3", "target_keyword": "lofi", "reason": "karena Z"},
        ],
        "saved": [
            {"id": "a", "title": "T1", "status": "SCHEDULED", "publish_date": "2026-08-12"},
        ],
    }
    monkeypatch.setattr("app.routers.ai.generate_content_patterns", lambda db, ch, days: canned)

    resp = client.post(
        "/api/ai/content-patterns",
        headers=auth_headers,
        json={"channel_id": ch.id, "days": 28},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["recommendations"]) == 3
    assert body["saved"][0]["status"] == "SCHEDULED"


def test_generate_content_patterns_requires_ai(db_session):
    from app.ai.service import generate_content_patterns
    from app.utils.errors import AppError

    ch = _seed_channel(db_session, _user(db_session))
    with pytest.raises(AppError):
        generate_content_patterns(db_session, ch)
