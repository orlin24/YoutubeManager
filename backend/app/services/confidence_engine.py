"""Confidence Engine.

Evidence-first confidence: every recommendation carries a confidence that is
derived from the amount and quality of the data behind it, never from vibes.

confidence_score    : 0-100 internal score (heuristic, NOT an official metric)
confidence_level    : INSUFFICIENT_DATA | LOW | MEDIUM | HIGH
data_quality        : INSUFFICIENT | POOR | FAIR | GOOD | EXCELLENT
sample_size         : how many data points support the claim
evidence_count      : how many distinct pieces of evidence support it

Confidence decays over time when a pattern stops performing (confidence decay),
but historical evidence is never deleted - it just stops being treated as truth.
"""
from __future__ import annotations

from typing import Any

LEVELS = ("INSUFFICIENT_DATA", "LOW", "MEDIUM", "HIGH")
MIN_SAMPLE = 3  # below this: INSUFFICIENT_DATA


def level_from_score(score: float | None) -> str:
    """Map an internal 0-100 score to a confidence level."""
    if score is None or score <= 0:
        return "INSUFFICIENT_DATA"
    if score < 35:
        return "LOW"
    if score < 65:
        return "MEDIUM"
    return "HIGH"


def level_to_value(level: str) -> float:
    """Normalize a level to a numeric value (for arithmetic)."""
    return {"INSUFFICIENT_DATA": 0.0, "LOW": 25.0, "MEDIUM": 55.0, "HIGH": 80.0}.get(level.upper(), 0.0)


def data_quality_score(
    sample_size: int,
    recency_days: int | None = None,
    missing_metrics: int = 0,
    historical_depth_days: int | None = None,
    outliers: int = 0,
    volatility: float = 0.0,
) -> dict[str, Any]:
    """0-100 data quality score with an explicit breakdown.

    Checks (per audit): data count, recency, missing metrics, historical depth,
    outliers, volatility. Poor data forces the AI to lower its confidence.
    """
    score = 50.0
    checks: list[str] = []

    if sample_size >= 10:
        score += 20
        checks.append("data cukup")
    elif sample_size >= 3:
        score += 10
        checks.append("data terbatas")
    else:
        score -= 20
        checks.append("data sangat sedikit")

    if recency_days is not None:
        if recency_days <= 7:
            score += 5
            checks.append("data terbaru")
        elif recency_days <= 30:
            checks.append("data cukup baru")
        else:
            score -= 10
            checks.append("data lama")

    if historical_depth_days is not None:
        if historical_depth_days >= 60:
            score += 5
            checks.append("riwayat panjang")
        elif historical_depth_days >= 28:
            checks.append("riwayat cukup")
        else:
            score -= 5
            checks.append("riwayat pendek")

    if missing_metrics > 0:
        score -= min(15, missing_metrics * 5)
        checks.append(f"{missing_metrics} metrik hilang")

    if outliers > 0:
        score -= min(10, outliers * 4)
        checks.append(f"{outliers} outlier")

    if volatility and volatility > 0.6:
        score -= 10
        checks.append("data volatil")
    elif volatility and volatility > 0.3:
        score -= 5
        checks.append("data agak volatil")

    score = max(5, min(98, score))
    if score >= 80:
        level = "EXCELLENT"
    elif score >= 60:
        level = "GOOD"
    elif score >= 40:
        level = "FAIR"
    elif score >= 25:
        level = "POOR"
    else:
        level = "INSUFFICIENT"
    return {
        "score": round(score, 1),
        "level": level,
        "checks": checks,
    }


def confidence_score(
    sample_size: int,
    evidence_count: int,
    data_quality: int | dict[str, Any] = 50,
    volatility: float = 0.0,
) -> float:
    """Internal 0-100 confidence: more samples + more evidence + better data.

    Returns 0 when the sample is too small to say anything.
    """
    if sample_size < MIN_SAMPLE:
        return 0.0
    dq = data_quality if isinstance(data_quality, (int, float)) else (data_quality or {}).get("score", 50)
    score = 40.0
    score += min(25, sample_size * 1.8)
    score += min(15, evidence_count * 5)
    score += (float(dq) - 50) * 0.4
    score -= min(10, volatility * 25)
    return round(max(0.0, min(95.0, score)), 1)


def confidence_payload(
    sample_size: int,
    evidence_count: int = 1,
    data_quality: int | dict[str, Any] = 50,
    volatility: float = 0.0,
) -> dict[str, Any]:
    """The standard confidence block every recommendation must carry."""
    score = confidence_score(sample_size, evidence_count, data_quality, volatility)
    return {
        "confidence_score": score,
        "confidence_level": level_from_score(score),
        "sample_size": sample_size,
        "evidence_count": evidence_count,
        "data_quality": data_quality if isinstance(data_quality, dict) else {"score": data_quality},
    }


def decay_confidence(score: float, age_days: int, recent_performance: float | None = None) -> float:
    """Confidence decay: old patterns are not assumed to stay true forever.

    age_days          : days since the pattern was last confirmed
    recent_performance: signed % vs expected; negative -> faster decay,
                        strongly positive -> keeps the confidence up.
    """
    if score <= 0:
        return 0.0
    decay = 0.0
    if age_days > 30:
        decay += (age_days - 30) * 0.5  # -0.5/day beyond 30 days
    elif age_days > 14:
        decay += (age_days - 14) * 0.25
    if recent_performance is not None:
        if recent_performance < -30:
            decay += 15
        elif recent_performance < 0:
            decay += 8
        elif recent_performance > 30:
            decay -= 10
    return round(max(0.0, min(95.0, score - decay)), 1)


def level_human(level: str) -> str:
    """Human-friendly Indonesian text for UI (rule #24: no technical jargon)."""
    return {
        "INSUFFICIENT_DATA": "Data belum cukup",
        "LOW": "Keyakinan rendah",
        "MEDIUM": "Keyakinan sedang",
        "HIGH": "Keyakinan tinggi",
        "EXCELLENT": "Kualitas data baik",
        "GOOD": "Kualitas data cukup",
        "FAIR": "Kualitas data sedang",
        "POOR": "Kualitas data rendah",
        "INSUFFICIENT": "Data belum cukup",
    }.get(level, level)
