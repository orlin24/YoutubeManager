from __future__ import annotations

from types import SimpleNamespace

from app.agents.decision_engine import compute_video_score


def _video(views=1000, ctr=0.05, avg_dur=120.0, likes=50, comments=10):
    return SimpleNamespace(
        view_count=views,
        ctr=ctr,
        average_view_duration_seconds=avg_dur,
        like_count=likes,
        comment_count=comments,
        published_at="2025-01-01T00:00:00+00:00",
    )


def test_score_in_range_and_strengths():
    result = compute_video_score(_video())
    assert 0.0 <= result["score"] <= 100.0
    assert isinstance(result["strengths"], list)
    assert isinstance(result["weaknesses"], list)
    assert result["ai"] is False


def test_high_ctr_scores_higher():
    low = compute_video_score(_video(views=1000, ctr=0.01))
    high = compute_video_score(_video(views=1000, ctr=0.08))
    assert high["score"] > low["score"]


def test_missing_data_returns_none_score():
    result = compute_video_score(SimpleNamespace(view_count=0, ctr=None,
                                                 average_view_duration_seconds=None,
                                                 like_count=0, comment_count=0,
                                                 published_at=None))
    assert result["score"] is None
    assert result["weaknesses"]


def test_custom_weights_respected():
    weights = {"ctr": 1.0, "retention": 0.0, "views_velocity": 0.0,
               "subscriber_conversion": 0.0, "watch_time": 0.0, "engagement": 0.0}
    result = compute_video_score(_video(views=1000, ctr=0.08), weights=weights)
    assert result["score"] > 50


def test_long_form_music_video_scores_well():
    # 1h+ music album: 50% avg view duration and 6% CTR = strong video
    video = SimpleNamespace(
        view_count=5000,
        ctr=0.06,
        average_view_duration_seconds=1800.0,  # 30 min watched of 60 min
        duration_seconds=3600,
        like_count=100,
        comment_count=5,
        published_at="2025-01-01T00:00:00+00:00",
    )
    snap = {"views": 5000, "watch_time_seconds": 5000 * 1800, "subscribers_gained": 5}
    result = compute_video_score(video, snapshot_agg=snap)
    assert result["score"] is not None
    assert 40 <= result["score"] <= 100, result
    # retention must be differentiated for long-form (not capped at 6 min)
    assert "Average view duration" in result["strengths"] or "Total watch time" in result["strengths"]


def test_ctr_six_percent_is_strong():
    result = compute_video_score(_video(views=5000, ctr=0.06))
    assert result["score"] is not None
    # 6% CTR should contribute a strong (>0.5) component
    ctr_only = compute_video_score(
        SimpleNamespace(view_count=1, ctr=0.06, average_view_duration_seconds=None,
                        like_count=0, comment_count=0, published_at=None),
        weights={"ctr": 1.0, "retention": 0.0, "views_velocity": 0.0,
                 "subscriber_conversion": 0.0, "watch_time": 0.0, "engagement": 0.0},
    )
    assert ctr_only["score"] > 50  # 0.06/0.08 = 0.75 -> 75
