"""Tests for the Business Intelligence engine."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.bi import ForecastHistory
from app.models.channel import Channel
from app.models.lifecycle import ChannelLifecycle
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services import bi_engine
from app.services.encryption import encrypt_str


def _seed(db, videos: list[tuple[int, int]]):
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
    for i, (views, days_ago) in enumerate(videos):
        db.add(Video(id=str(uuid.uuid4()), channel_id=ch.id, youtube_video_id=f"v{i}",
                     title=f"V{i}", view_count=views, like_count=1, comment_count=0,
                     published_at=now - timedelta(days=days_ago)))
    db.commit()
    return ch


def test_analyze_series_insufficient_data():
    r = bi_engine.analyze_series([10, 20, 30])
    assert r["status"] == "INSUFFICIENT_DATA"


def test_analyze_series_forecast_range():
    values = [100 + (i % 7) * 5 for i in range(30)]
    r = bi_engine.analyze_series(values)
    assert r["status"] == "OK"
    f = r["forecast"]
    assert f["lower"] <= f["expected"] <= f["upper"]
    assert 0 <= f["confidence"] <= 100
    assert r["trend"] in ("growing", "stable", "declining", "volatile")


def test_analyze_series_detects_decline():
    values = [100 - i * 3 for i in range(30)]
    r = bi_engine.analyze_series(values)
    assert r["trend"] == "declining"
    assert r["change_pct"] < -5


def test_forecast_saves_history(db_session):
    ch = _seed(db_session, [(2000 - i * 40, i) for i in range(20)])
    f = bi_engine.forecast(db_session, ch.id, "views", 30, save=True)
    assert f["status"] in ("OK", "INSUFFICIENT_DATA")
    if f["status"] == "OK":
        assert f["forecast"]["lower"] <= f["forecast"]["expected"] <= f["forecast"]["upper"]
        assert db_session.query(ForecastHistory).filter_by(channel_id=ch.id).count() >= 1


def test_risk_and_opportunity_scan(db_session):
    ch = _seed(db_session, [(100, i) for i in range(10)])
    lc = ChannelLifecycle(channel_id=ch.id, mode="RECOVERY", objective="x", health_score=30,
                          growth_pct=-50.0, data={"risk": {"level": "HIGH", "reason": "duplikat",
                                                           "category": "REPETITIVE_CONTENT_RISK",
                                                           "risk_score": 60.0, "severity": "HIGH",
                                                           "confidence": "MEDIUM", "sample_size": 10,
                                                           "evidence": "5 video mirip"},
                                                  "winners": [{"category": "VIEW WINNER", "title": "W",
                                                               "pattern_status": "PROVEN",
                                                               "confidence": "HIGH", "data": {"views": 5000},
                                                               "note": "pemenang",
                                                               "baseline": {"median": 100, "sample_size": 10}}],
                                                  "priorities": []})
    db_session.add(lc)
    db_session.commit()
    risks = bi_engine.risk_scan(db_session, ch, lc)
    # audit #1/#3: HIGH similarity risk must NOT auto-escalate to CRITICAL
    assert not any(r["severity"] == "CRITICAL" for r in risks)
    assert any(r["severity"] == "HIGH" for r in risks)  # recovery + content risk
    opps = bi_engine.opportunity_scan(db_session, ch, lc)
    assert opps and opps[0]["category"] == "Winning Formula"


def test_simulate_best_base_worst():
    r = bi_engine.simulate({"name": "5x/minggu", "uploads_per_week": 5}, {"uploads_per_week": 2, "views_per_upload": 1000})
    assert r["model_estimate"] is True
    assert r["best_case"]["views_delta_pct"] >= r["base_case"]["views_delta_pct"] >= r["worst_case"]["views_delta_pct"]
    assert r["production_load_delta_pct"] > 0


def test_classify():
    lc = ChannelLifecycle(channel_id="x", mode="SCALE", objective="", health_score=80, growth_pct=20.0)
    assert bi_engine.classify_channel(lc, "growing")["class"] == "SCALE"
    lc2 = ChannelLifecycle(channel_id="x", mode="NEW", objective="", health_score=50, growth_pct=0.0)
    assert bi_engine.classify_channel(lc2, "stable")["class"] == "EXPERIMENT"


def test_optimize_respects_constraints(db_session):
    ids = [c.id for c in (_seed(db_session, [(100, i) for i in range(5)]),)]
    r = bi_engine.optimize(db_session, list(ids), {"max_videos_per_day": 2})
    assert sum(i["share"] for i in r["items"]) <= 100.1
    assert r["items"][0]["videos_per_week"] <= 14


def test_accuracy_insufficient(db_session):
    r = bi_engine.forecast_accuracy(db_session)
    assert r["status"] in ("OK", "INSUFFICIENT_DATA")
