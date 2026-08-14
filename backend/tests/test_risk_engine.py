"""Audit tests for Risk Engine, Confidence Engine and Automatic Learning.

TEST 1 : 6 judul mirip -> REPETITIVE_CONTENT_RISK, BUKAN COPYRIGHT_RISK, bukan CRITICAL
TEST 2 : 1 video viral -> OUTLIER, bukan PROVEN_WINNER
TEST 3 : 3 video bagus pola sama -> PROMISING
TEST 4 : 10+ video pola sama outperform baseline -> WINNING_PATTERN
TEST 5 : channel menurun + 1 video bagus -> CHANNEL MENURUN + VIDEO OUTPERFORMING
TEST 6 : forecast data sedikit -> INSUFFICIENT_DATA
TEST 7 : memori rekomendasi mempengaruhi keputusan AI (konteks berubah)
TEST 8 : rekomendasi gagal -> confidence turun
TEST 9 : rekomendasi sukses berulang -> confidence naik
E2E   : loop penuh belajar otomatis (record -> hasil -> evaluasi -> memori -> konteks)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.ai.memory import build_context
from app.models.channel import Channel
from app.models.learning import LearningMemory
from app.models.user import User
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services import bi_engine, learning_service, lifecycle_service, risk_engine
from app.services.encryption import encrypt_str


def _make_channel(db, name="Ch A", channel_id=None) -> Channel:
    channel_id = channel_id or f"UC{uuid4().hex[:10]}"
    user = User(id=str(uuid4()), email=f"u{uuid4().hex[:8]}@example.com", name="U", password_hash="x")
    db.add(user)
    db.flush()
    acc = YouTubeAccount(
        id=str(uuid4()), user_id=user.id, google_account_email="g@gmail.com",
        channel_id=channel_id, channel_title=name,
        access_token_encrypted=encrypt_str("a"), refresh_token_encrypted=encrypt_str("r"),
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(acc)
    db.flush()
    ch = Channel(
        id=str(uuid4()), youtube_account_id=acc.id, channel_id=channel_id,
        title=name, subscriber_count=100, video_count=0,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def _make_video(db, channel: Channel, title: str, views: int, days_ago: int, yid: str) -> Video:
    v = Video(
        channel_id=channel.id, title=title, view_count=views,
        published_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        youtube_video_id=yid, privacy_status="public",
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


# ---- TEST 1 -----------------------------------------------------------------
def test_similar_titles_repetitive_risk_not_copyright(db_session):
    ch = _make_channel(db_session)
    titles = [
        "SUMPAH MERINDING KAMU HARUS TAHU", "SUMPAH MERINDING INI HEBAT",
        "SUMPAH MERINDING JANGAN DI SKIP", "SUMPAH MERINDING FAKTA BARU",
        "SUMPAH MERINDING WAJIB NONTON", "SUMPAH MERINDING GILA",
    ]
    for i, t in enumerate(titles):
        _make_video(db_session, ch, t, views=1000, days_ago=i, yid=f"v{i}")
    risk = lifecycle_service._title_risk(db_session.query(Video).filter(Video.channel_id == ch.id).all())
    assert risk["category"] == "REPETITIVE_CONTENT_RISK"
    assert risk["category"] != "COPYRIGHT_RISK"
    assert "hak cipta" not in risk["reason"].lower()
    assert risk["severity"] in ("MEDIUM", "HIGH")
    assert risk["severity"] != "CRITICAL"
    assert risk["risk_score"] is not None and 0 <= risk["risk_score"] <= 82
    assert risk["sample_size"] == 6
    assert risk["recommended_action"]


# ---- TEST 2 -----------------------------------------------------------------
def test_single_viral_video_is_outlier_not_winner(db_session):
    ch = _make_channel(db_session)
    _make_video(db_session, ch, "Biasa 1", views=100, days_ago=30, yid="v1")
    _make_video(db_session, ch, "Biasa 2", views=120, days_ago=20, yid="v2")
    _make_video(db_session, ch, "VIRAL SEKALI", views=50000, days_ago=10, yid="v3")
    winners = lifecycle_service.detect_winners(db_session, ch)
    vw = [w for w in winners if w["category"] == "VIEW WINNER"]
    assert vw, "harus ada VIEW WINNER (fakta video teratas)"
    assert vw[0]["pattern_status"] == "OUTLIER", "1 video viral bukan pola terbukti"
    assert vw[0]["confidence"] == "LOW"
    # opportunity_scan (BI) harus menolak OUTLIER sebagai peluang
    lc = lifecycle_service.run_channel_analysis(db_session, ch)
    opps = bi_engine.opportunity_scan(db_session, ch, None)
    assert not any(o["experiment_status"] == "PROVEN" for o in opps)


# ---- TEST 3 -----------------------------------------------------------------
def test_three_videos_same_pattern_promising(db_session):
    ch = _make_channel(db_session)
    _make_video(db_session, ch, "DUIT MALAM INI episode 1", views=2000, days_ago=30, yid="v1")
    _make_video(db_session, ch, "DUIT MALAM INI episode 2", views=3000, days_ago=20, yid="v2")
    _make_video(db_session, ch, "DUIT MALAM INI episode 3", views=5000, days_ago=10, yid="v3")
    _make_video(db_session, ch, "Konten lain", views=150, days_ago=5, yid="v4")
    winners = lifecycle_service.detect_winners(db_session, ch)
    vw = [w for w in winners if w["category"] == "VIEW WINNER"][0]
    assert vw["pattern_status"] == "PROMISING"
    assert vw["confidence"] == "MEDIUM"
    assert vw["baseline"]["median"] > 0


# ---- TEST 4 -----------------------------------------------------------------
def test_repeated_pattern_proven_winner(db_session):
    ch = _make_channel(db_session)
    for i in range(12):
        _make_video(db_session, ch, f"PODCAST PANJANG episode {i}", views=3000, days_ago=60 - i, yid=f"p{i}")
    for i in range(30):
        _make_video(db_session, ch, f"Video acak {i}", views=80, days_ago=30 + i, yid=f"r{i}")
    winners = lifecycle_service.detect_winners(db_session, ch)
    vw = [w for w in winners if w["category"] == "VIEW WINNER"][0]
    assert vw["pattern_status"] == "PROVEN"
    assert vw["confidence"] == "HIGH"
    # median channel jauh di bawah pola pemenang (baseline, bukan mode)
    assert vw["baseline"]["median"] < 1000
    assert vw["baseline"]["ratio_vs_median"] > 2


# ---- TEST 5 -----------------------------------------------------------------
def test_channel_declining_vs_video_outperforming_separated(db_session):
    ch = _make_channel(db_session)
    # channel secara keseluruhan menurun (views 28 hari vs sebelumnya)
    for i in range(4):
        _make_video(db_session, ch, f"Lama {i}", views=5000, days_ago=50 - i * 6, yid=f"l{i}")
    for i in range(4):
        _make_video(db_session, ch, f"Baru {i}", views=300, days_ago=10 - i, yid=f"b{i}")
    result = lifecycle_service.run_channel_analysis(db_session, ch)
    # 1) level channel: menurun / RECOVERY
    assert result["mode"] in ("RECOVERY",)
    perf = [r for r in result["risks"] if r["category"] in ("PERFORMANCE_RISK", "CHANNEL_HEALTH_RISK")]
    assert perf and perf[0]["severity"] in ("MEDIUM", "HIGH")
    assert perf[0]["severity"] != "CRITICAL"  # penurunan views saja bukan CRITICAL
    # 2) satu video outperform baseline = fakta video, bukan klaim channel tumbuh
    vw = [w for w in result["winners"] if w["category"] == "VIEW WINNER"][0]
    assert vw["pattern_status"] in ("OUTLIER", "INCONCLUSIVE")


# ---- TEST 6 -----------------------------------------------------------------
def test_forecast_insufficient_data(db_session):
    ch = _make_channel(db_session)
    # data sangat sedikit (3 titik < MIN_SAMPLES=7) -> jujur: belum cukup data
    for i in range(3):
        _make_video(db_session, ch, f"v{i}", views=100 + i, days_ago=10 - i, yid=f"f{i}")
    f = bi_engine.forecast(db_session, ch.id, "views", 7, save=False)
    assert f["status"] == "INSUFFICIENT_DATA"
    assert f["sample_size"] == 3
    # cukup data tapi tidak stabil -> forecast mengakui ketidakpastian (rentang)
    for i in range(8):
        _make_video(db_session, ch, f"w{i}", views=[5000, 40, 7000, 60, 100, 9000, 80, 200][i],
                    days_ago=30 - i, yid=f"w{i}")
    f2 = bi_engine.forecast(db_session, ch.id, "views", 7, save=False)
    assert f2["status"] == "OK"
    assert f2["data_quality"]["level"] in ("POOR", "FAIR", "INSUFFICIENT")
    assert "belum cukup" in f2["interpretation"].lower() or "perkiraan" in f2["interpretation"].lower()
    # forecast bukan kepastian: selalu punya rentang atas-bawah
    assert f2["forecast"]["upper"] >= f2["forecast"]["expected"] >= f2["forecast"]["lower"]


# ---- TEST 7 -----------------------------------------------------------------
def test_learning_memory_changes_ai_context(db_session):
    ch = _make_channel(db_session)
    _make_video(db_session, ch, "konten", views=100, days_ago=1, yid="ctx1")
    ctx_before = build_context(db_session, ch, "rekomendasi strategi konten")
    assert ctx_before["learning_memory"]["has_memory"] is False
    # simulasikan pola GAGAL yang terekam di memori
    db_session.add(LearningMemory(
        channel_id=ch.id, kind="FAILED_PATTERN",
        pattern="Judul clickbait tanpa isi",
        evidence="3 eksperimen gagal", sample_size=3, confidence=10.0,
        performance="0.3x median channel",
    ))
    db_session.commit()
    ctx_after = build_context(db_session, ch, "rekomendasi strategi konten")
    assert ctx_after["learning_memory"]["has_memory"] is True
    assert any(m["pattern"] == "Judul clickbait tanpa isi" for m in ctx_after["learning_memory"]["failed_patterns"])
    # konteks berubah karena memori: AI melihat pola yang gagal
    assert "clickbait" in ctx_after["learning_memory"]["failed_patterns"][0]["pattern"].lower()


# ---- TEST 8 -----------------------------------------------------------------
def test_failed_recommendation_lowers_confidence(db_session):
    ch = _make_channel(db_session)
    _make_video(db_session, ch, "baseline lama", views=5000, days_ago=60, yid="bl")
    out = learning_service.record_recommendation(
        db_session, ch.id, decision="Uji pola X", evidence="pola terlihat",
        sample_size=5, confidence="MEDIUM", expected_outcome="2x median",
        expected_value=4000.0,
    )
    # hasil aktual jauh di bawah target (video baru sedikit views)
    _make_video(db_session, ch, "hasil uji", views=300, days_ago=1, yid="hasil")
    out.created_at = datetime.now(timezone.utc) - timedelta(days=14)  # sudah lewat masa evaluasi
    db_session.commit()
    learning_service.evaluate_outcomes(db_session)
    db_session.refresh(out)
    assert out.status == "evaluated"
    failed = db_session.query(LearningMemory).filter(
        LearningMemory.channel_id == ch.id, LearningMemory.kind == "FAILED_PATTERN").all()
    assert failed, "rekomendasi gagal harus terekam sebagai FAILED_PATTERN"
    assert failed[0].confidence < 30
    # audit trail confidence sebelum/sesudah
    history = db_session.query(LearningMemory).filter(
        LearningMemory.channel_id == ch.id, LearningMemory.kind == "CONFIDENCE_HISTORY").all()
    assert history


# ---- TEST 9 -----------------------------------------------------------------
def test_repeated_success_raises_confidence(db_session):
    ch = _make_channel(db_session)
    _make_video(db_session, ch, "baseline lama", views=2000, days_ago=60, yid="bl")
    out1 = learning_service.record_recommendation(
        db_session, ch.id, decision="Uji pola sukses", evidence="data",
        sample_size=4, confidence="LOW", expected_outcome="2x median",
        expected_value=300.0,
    )
    out1.created_at = datetime.now(timezone.utc) - timedelta(days=20)
    _make_video(db_session, ch, "hasil 1", views=1500, days_ago=15, yid="h1")
    db_session.commit()
    learning_service.evaluate_outcomes(db_session)

    mem1 = db_session.query(LearningMemory).filter(
        LearningMemory.channel_id == ch.id, LearningMemory.kind == "WINNING_PATTERN").first()
    assert mem1 is not None
    c1 = mem1.confidence

    # sukses kedua: confidence harus naik
    out2 = learning_service.record_recommendation(
        db_session, ch.id, decision="Uji pola sukses", evidence="data",
        sample_size=4, confidence="LOW", expected_outcome="2x median",
        expected_value=300.0,
    )
    out2.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    _make_video(db_session, ch, "hasil 2", views=2000, days_ago=3, yid="h2")
    db_session.commit()
    learning_service.evaluate_outcomes(db_session)

    mem2 = db_session.query(LearningMemory).filter(
        LearningMemory.channel_id == ch.id, LearningMemory.kind == "WINNING_PATTERN").first()
    assert mem2.confidence > c1, "sukses berulang harus menaikkan confidence"


# ---- regression: SQLite (Pi) naive vs aware datetimes -----------------------
def test_sqlite_naive_datetime_no_crash(db_session):
    """Pi pakai SQLite -> published_at/created_at/updated_at naive. Aritmetika
    datetime harus tetap jalan (regresi: 'can't subtract offset-naive and
    offset-aware datetimes' di /ai/ceo)."""
    from app.models.channel_profile import ChannelProfile

    ch = _make_channel(db_session)
    _make_video(db_session, ch, "lama", views=100, days_ago=40, yid="n1")
    # simulasikan SQLite: published_at naive
    v = db_session.query(Video).filter(Video.channel_id == ch.id).first()
    v.published_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40)
    db_session.add(ChannelProfile(channel_id=ch.id, upload_cadence_days=1))
    db_session.commit()
    # risk_scan (dipanggil scorecard CEO) tidak boleh crash
    risks = bi_engine.risk_scan(db_session, ch, None)
    assert any("jadwal" in r.get("category", "").lower() or "upload" in r.get("category", "").lower() for r in risks)
    # learning: created_at naive + evaluasi tidak boleh crash
    out = learning_service.record_recommendation(
        db_session, ch.id, decision="Uji tz", evidence="x", sample_size=2,
        confidence="LOW", expected_outcome="2x", expected_value=5000.0,
    )
    out.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=20)
    _make_video(db_session, ch, "hasil uji", views=50, days_ago=5, yid="n2")
    db_session.commit()
    res = learning_service.evaluate_outcomes(db_session)
    assert res["evaluated"] >= 1
    # decay dengan updated_at naive tidak boleh crash
    db_session.add(LearningMemory(
        channel_id=ch.id, kind="WINNING_PATTERN", pattern="pola lama", sample_size=5,
        confidence=60.0, performance="x",
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40),
    ))
    db_session.commit()
    learning_service._apply_decay_to_patterns(db_session)


# ---- learning dashboard endpoint -------------------------------------------
def test_learning_endpoints_smoke(client):
    r1 = client.get("/api/learning/stats")
    assert r1.status_code == 200
    assert "strategy_version" in r1.json()
    r2 = client.get("/api/learning/memory")
    assert r2.status_code == 200
    r3 = client.get("/api/learning/outcomes")
    assert r3.status_code == 200
    r4 = client.post("/api/learning/evaluate")
    assert r4.status_code == 200
    assert "evaluated" in r4.json()


# ---- E2E --------------------------------------------------------------------
def test_e2e_learning_loop(db_session):
    """Loop penuh: rekomendasi -> hasil -> evaluasi -> memori -> konteks AI."""
    ch = _make_channel(db_session)
    for i in range(6):
        _make_video(db_session, ch, f"baseline {i}", views=1000, days_ago=80 - i, yid=f"e{i}")
    # 1. AI merekomendasikan pola (recorded)
    out = learning_service.record_recommendation(
        db_session, ch.id, decision="Uji pola: JUDUL X",
        reason="analisis", evidence="pola", sample_size=6,
        confidence="MEDIUM", expected_outcome="2x median",
        expected_value=2000.0,
    )
    # 2. video eksperimen dipublikasikan dan performa bagus
    _make_video(db_session, ch, "JUDUL X (eksperimen)", views=2500, days_ago=5, yid="exp1")
    out.created_at = datetime.now(timezone.utc) - timedelta(days=9)
    db_session.commit()
    # 3. evaluasi otomatis membandingkan expected vs actual
    res = learning_service.evaluate_outcomes(db_session)
    assert res["evaluated"] >= 1
    # 4. memori: pola pemenang tersimpan + confidence history
    win = db_session.query(LearningMemory).filter(
        LearningMemory.channel_id == ch.id, LearningMemory.kind == "WINNING_PATTERN").all()
    assert win
    strat = db_session.query(LearningMemory).filter(
        LearningMemory.kind == "STRATEGY_HISTORY").order_by(LearningMemory.created_at.desc()).first()
    assert strat is not None
    # 5. konteks AI berikutnya memuat memori tsb (keputusan berubah)
    ctx = build_context(db_session, ch, "strategi baru")
    assert ctx["learning_memory"]["has_memory"] is True
    assert ctx["learning_memory"]["winning_patterns"]
    assert ctx["learning_memory"]["strategy_version"] >= 1
