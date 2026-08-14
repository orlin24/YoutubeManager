"""Risk Engine.

Evidence-first risk assessment with separated categories and a severity scale
that refuses to cry wolf. A similar title is NEVER automatically a copyright or
monetization violation; CRITICAL requires strong evidence, big impact, urgency
and sufficient confidence. Without evidence the answer is INSUFFICIENT_DATA.

Categories (audit #2):
  COPYRIGHT_RISK, REPETITIVE_CONTENT_RISK, MONETIZATION_RISK, POLICY_RISK,
  CHANNEL_HEALTH_RISK, PERFORMANCE_RISK, SECURITY_RISK, UPLOAD_RISK, TECHNICAL_RISK

Every risk carries: risk_score, severity, confidence, evidence, sample_size,
reason, recommended_action (audit #4).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.services.confidence_engine import confidence_payload, level_from_score

RISK_CATEGORIES = [
    "COPYRIGHT_RISK", "REPETITIVE_CONTENT_RISK", "MONETIZATION_RISK", "POLICY_RISK",
    "CHANNEL_HEALTH_RISK", "PERFORMANCE_RISK", "SECURITY_RISK", "UPLOAD_RISK", "TECHNICAL_RISK",
]

RISK_CATEGORY_LABELS = {
    "COPYRIGHT_RISK": "Risiko hak cipta",
    "REPETITIVE_CONTENT_RISK": "Risiko konten repetitif",
    "MONETIZATION_RISK": "Risiko monetisasi",
    "POLICY_RISK": "Risiko kebijakan",
    "CHANNEL_HEALTH_RISK": "Risiko kesehatan channel",
    "PERFORMANCE_RISK": "Risiko performa",
    "SECURITY_RISK": "Risiko keamanan",
    "UPLOAD_RISK": "Risiko jadwal upload",
    "TECHNICAL_RISK": "Risiko teknis",
}

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_UNKNOWN = "INSUFFICIENT_DATA"

# CRITICAL must be earned: score high AND confidence high AND big impact.
_CRITICAL_MIN_SCORE = 78
_HIGH_MIN_SCORE = 55
_MEDIUM_MIN_SCORE = 28


def severity_from_score(score: float, confidence_level: str = "HIGH", allow_critical: bool = True) -> str:
    """Map an internal 0-100 score to LOW/MEDIUM/HIGH/CRITICAL.

    CRITICAL additionally requires sufficient confidence - otherwise the risk
    is capped at HIGH so we never claim a crisis we cannot back with data.
    """
    if score is None:
        return _UNKNOWN
    if score >= _CRITICAL_MIN_SCORE and allow_critical and confidence_level in ("MEDIUM", "HIGH"):
        return "CRITICAL"
    if score >= _HIGH_MIN_SCORE:
        return "HIGH"
    if score >= _MEDIUM_MIN_SCORE:
        return "MEDIUM"
    return "LOW"


def build_risk(
    category: str,
    risk_score: float | None,
    confidence_level: str,
    evidence: str,
    sample_size: int,
    reason: str,
    recommended_action: str,
    allow_critical: bool = True,
) -> dict[str, Any]:
    """Standard risk dict (audit #4): score, severity, confidence, evidence,
    sample_size, reason, recommended_action."""
    if category not in RISK_CATEGORIES:
        raise ValueError(f"Unknown risk category: {category}")
    severity = severity_from_score(risk_score, confidence_level, allow_critical) if risk_score is not None else _UNKNOWN
    return {
        "category": category,
        "category_label": RISK_CATEGORY_LABELS[category],
        "risk_score": risk_score,
        "severity": severity,
        "confidence": confidence_level,
        "confidence_score": (confidence_payload(sample_size, 1, 50)["confidence_score"] if risk_score is not None else 0.0),
        "evidence": evidence,
        "sample_size": sample_size,
        "reason": reason,
        "recommended_action": recommended_action,
    }


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/spaces for similarity grouping."""
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


_PREFIX_LEN = 15  # shared leading phrase length (e.g. 'sumpahmerinding')
_MIN_PHRASE = 8   # ignore accidental matches on very short prefixes


def _title_groups(videos: list[Any]) -> tuple[dict[str, list[Any]], dict[str, list[Any]]]:
    """Group videos by exact normalized title and by shared leading phrase.

    Returns (exact_groups, prefix_groups). Two titles sharing the first 15
    normalized characters (a real phrase like 'SUMPAH MERINDING') are treated
    as near-duplicate formulas; prefixes shorter than 8 chars are ignored.
    """
    exact: dict[str, list[Any]] = {}
    prefix: dict[str, list[Any]] = {}
    for v in videos:
        title = getattr(v, "title", "") or ""
        norm = _normalize_title(title)
        if not norm:
            continue
        exact.setdefault(norm, []).append(v)
        key = norm[:_PREFIX_LEN]
        if len(key) >= _MIN_PHRASE:
            prefix.setdefault(key, []).append(v)
    return exact, prefix


def assess_repetitive_content(videos: list[Any]) -> dict[str, Any]:
    """Similar / duplicate titles -> REPETITIVE_CONTENT_RISK.

    Never COPYRIGHT_RISK, never MONETIZATION_RISK (audit #1). Similarity alone
    is capped at HIGH severity - it becomes CRITICAL only when an extreme
    fraction of the channel is near-identical AND confidence is high AND the
    sample is large (audit #3).
    """
    exact, prefix = _title_groups(videos)
    total = len(videos)

    def biggest_group(groups: dict[str, list[Any]]) -> tuple[int, str]:
        if not groups:
            return 0, ""
        title, group = max(groups.items(), key=lambda kv: len(kv[1]))
        return len(group), group[0].title if hasattr(group[0], "title") else ""

    exact_n, exact_title = biggest_group(exact)
    prefix_n, prefix_title = biggest_group(prefix)
    n = max(exact_n, prefix_n)

    if total == 0 or n < 2:
        return build_risk(
            "REPETITIVE_CONTENT_RISK", 0.0, "LOW",
            evidence="Belum ada indikasi judul berulang.",
            sample_size=total,
            reason="Belum cukup data untuk menilai risiko konten repetitif.",
            recommended_action="Pantau variasi judul pada upload berikutnya.",
        )

    ratio = n / total
    # score from ratio + absolute count. CRITICAL is reserved for EXTREME cases
    # (nearly the whole channel on the same title pattern) - similarity alone
    # stays at HIGH or below otherwise.
    score = min(82.0, 20 + ratio * 50 + min(10, n))
    confidence_level = "HIGH" if n >= 6 and ratio >= 0.4 else ("MEDIUM" if n >= 3 else "LOW")

    if n >= 10 and ratio >= 0.6:
        reason = f"{n} dari {total} judul video memiliki pola yang sangat mirip. Ini adalah sinyal konten yang kurang berbeda dan dapat menurunkan performa."
        action = "Audit konten dan tingkatkan diferensiasi judul/format."
    elif n >= 3:
        reason = f"{n} judul video memiliki pola yang sangat mirip. Risiko konten repetitif / kurang berbeda."
        action = "Periksa variasi judul dan sudut cerita pada konten mendatang."
    else:
        reason = f"Terdapat {n} judul dengan pola mirip. Sinyal lemah, pantau terus."
        action = "Pantau variasi judul."

    risk = build_risk(
        "REPETITIVE_CONTENT_RISK", score, confidence_level,
        evidence=f"{n} video memiliki pola judul sangat mirip" + (f" (contoh: {prefix_title[:60]})" if prefix_title else ""),
        sample_size=total,
        reason=reason,
        recommended_action=action,
    )
    # cap: similarity alone is CRITICAL only with an overwhelming, repeated pattern
    if n < 15 or ratio < 0.9:
        if risk["severity"] == "CRITICAL":
            risk["severity"] = "HIGH"
    elif risk["severity"] == "CRITICAL":
        risk["reason"] = (f"{n} dari {total} judul video memiliki pola yang hampir identik. "
                          "Ini indikasi kuat konten repetitif yang perlu ditindak segera.")
    return risk


def copyright_assessment(evidence: str | None = None, sample_size: int = 0) -> dict[str, Any]:
    """COPYRIGHT_RISK only with evidence. Without it: 'Belum cukup data'."""
    if not evidence:
        return build_risk(
            "COPYRIGHT_RISK", None, "INSUFFICIENT_DATA",
            evidence="Tidak ada indikasi pelanggaran hak cipta dari data yang tersedia.",
            sample_size=sample_size,
            reason="Belum cukup data untuk menilai risiko hak cipta.",
            recommended_action="Gunakan hanya konten orisinal atau yang memiliki lisensi.",
        )
    return build_risk(
        "COPYRIGHT_RISK", 70.0, "MEDIUM",
        evidence=evidence, sample_size=sample_size,
        reason="Terdapat indikasi yang perlu diaudit lebih lanjut terkait hak cipta.",
        recommended_action="Audit legal konten sebelum dipublikasikan.",
    )


def monetization_assessment(evidence: str | None = None, sample_size: int = 0) -> dict[str, Any]:
    """MONETIZATION_RISK only with concrete revenue/monetization evidence."""
    if not evidence:
        return build_risk(
            "MONETIZATION_RISK", None, "INSUFFICIENT_DATA",
            evidence="Tidak ada data pelanggaran monetisasi.",
            sample_size=sample_size,
            reason="Belum cukup data untuk menilai risiko monetisasi.",
            recommended_action="Pantau status monetisasi dan klaim konten.",
        )
    return build_risk(
        "MONETIZATION_RISK", 65.0, "MEDIUM", evidence=evidence, sample_size=sample_size,
        reason="Terdapat indikasi risiko monetisasi.",
        recommended_action="Tinjau kebijakan monetisasi YouTube.",
    )


def policy_assessment(evidence: str | None = None) -> dict[str, Any]:
    if not evidence:
        return build_risk(
            "POLICY_RISK", None, "INSUFFICIENT_DATA",
            evidence="Tidak ada indikasi pelanggaran kebijakan.",
            sample_size=0,
            reason="Belum cukup data untuk menilai risiko kebijakan.",
            recommended_action="Patuhi Pedoman Komunitas YouTube.",
        )
    return build_risk(
        "POLICY_RISK", 70.0, "MEDIUM", evidence=evidence, sample_size=0,
        reason="Terdapat indikasi yang perlu diperiksa terhadap kebijakan.",
        recommended_action="Periksa konten terhadap Pedoman Komunitas.",
    )


def security_assessment(evidence: str | None = None) -> dict[str, Any]:
    if not evidence:
        return build_risk(
            "SECURITY_RISK", None, "INSUFFICIENT_DATA",
            evidence="Tidak ada indikasi masalah keamanan akun.",
            sample_size=0,
            reason="Belum cukup data untuk menilai risiko keamanan.",
            recommended_action="Aktifkan verifikasi 2 langkah pada akun Google.",
        )
    return build_risk(
        "SECURITY_RISK", 75.0, "MEDIUM", evidence=evidence, sample_size=0,
        reason="Terdapat indikasi masalah keamanan.",
        recommended_action="Periksa sesi akun dan segera amankan kredensial.",
    )


def assess_technical(auth_error: str | None = None, last_sync_error: str | None = None) -> dict[str, Any]:
    """TECHNICAL_RISK from real signals (OAuth auth_error, sync errors)."""
    evidence = None
    if auth_error:
        evidence = f"Token OAuth bermasalah: {str(auth_error)[:120]}"
    elif last_sync_error:
        evidence = f"Sync terakhir gagal: {str(last_sync_error)[:120]}"
    if not evidence:
        return build_risk(
            "TECHNICAL_RISK", None, "INSUFFICIENT_DATA",
            evidence="Tidak ada masalah teknis terdeteksi.",
            sample_size=0,
            reason="Belum cukup data untuk menilai risiko teknis.",
            recommended_action="Pantau status koneksi YouTube.",
        )
    return build_risk(
        "TECHNICAL_RISK", 62.0, "MEDIUM", evidence=evidence, sample_size=1,
        reason="Ada masalah koneksi/teknis yang perlu diperbaiki.",
        recommended_action="Hubungkan ulang akun Google atau periksa log sync.",
    )


def assess_performance_decline(growth_pct: float | None, health_score: float | None) -> dict[str, Any]:
    """CHANNEL_HEALTH_RISK / PERFORMANCE_RISK from channel-level trend.

    A views decline alone is HIGH at most (audit #3 - CRITICAL is not for
    'views turun'). CRITICAL only if the channel is objectively collapsing
    (very low health + severe sustained decline) with a real sample.
    """
    if growth_pct is None or health_score is None:
        return build_risk(
            "PERFORMANCE_RISK", None, "INSUFFICIENT_DATA",
            evidence="Belum ada data perbandingan performa antar periode.",
            sample_size=0,
            reason="Belum cukup data untuk menilai performa channel.",
            recommended_action="Tunggu data beberapa periode untuk dibandingkan.",
        )
    if growth_pct >= -10:
        return build_risk(
            "PERFORMANCE_RISK", 15.0, "LOW",
            evidence=f"Performa relatif stabil (perubahan {growth_pct:+.1f}%).",
            sample_size=2,
            reason="Tidak ada indikasi penurunan performa yang berarti.",
            recommended_action="Lanjutkan strategi saat ini.",
        )
    score = min(72.0, 30 + abs(growth_pct) * 0.6 + max(0, 50 - (health_score or 50)) * 0.4)
    if growth_pct <= -50 and (health_score or 50) < 25:
        severity = "HIGH"
        reason = f"Channel sedang menurun ({growth_pct:+.1f}%) dengan kesehatan {health_score:.0f}/100."
    else:
        severity = "HIGH" if growth_pct <= -25 else "MEDIUM"
        reason = f"Views 28 hari turun {abs(growth_pct):.1f}% dibanding periode sebelumnya."
    return build_risk(
        "CHANNEL_HEALTH_RISK" if growth_pct <= -50 else "PERFORMANCE_RISK",
        score, "MEDIUM" if severity == "MEDIUM" else "HIGH",
        evidence=f"Tren channel {growth_pct:+.1f}% (28 hari vs 28 hari sebelumnya).",
        sample_size=2,
        reason=reason,
        recommended_action="Tinjau strategi konten; identifikasi video yang masih berperforma baik.",
        allow_critical=False,
    )


def assess_upload_consistency(cadence_days: int | None, last_upload_days_ago: int | None) -> dict[str, Any]:
    """UPLOAD_RISK from upload cadence (profile) vs last actual upload."""
    if not cadence_days or cadence_days <= 0 or last_upload_days_ago is None:
        return build_risk(
            "UPLOAD_RISK", None, "INSUFFICIENT_DATA",
            evidence="Belum ada jadwal upload atau data upload yang cukup.",
            sample_size=0,
            reason="Belum cukup data untuk menilai risiko jadwal upload.",
            recommended_action="Atur jadwal upload di Memori AI channel.",
        )
    overdue = last_upload_days_ago - cadence_days
    if overdue <= 0:
        return build_risk(
            "UPLOAD_RISK", 10.0, "LOW",
            evidence=f"Upload terakhir {last_upload_days_ago} hari lalu, jadwal {cadence_days} hari.",
            sample_size=1,
            reason="Jadwal upload masih terpenuhi.",
            recommended_action="Pertahankan konsistensi upload.",
        )
    score = min(60.0, 25 + overdue * 8)
    return build_risk(
        "UPLOAD_RISK", score, "MEDIUM" if overdue <= 3 else "HIGH",
        evidence=f"Terlambat {overdue} hari dari jadwal {cadence_days} hari.",
        sample_size=1,
        reason=f"Belum ada video baru {last_upload_days_ago} hari (jadwal {cadence_days} hari).",
        recommended_action="Upload konten baru segera untuk menjaga momentum.",
    )


def risk_severity_sort_key(severity: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INSUFFICIENT_DATA": 4}.get(severity, 9)


# ---- priority scoring (audit #14) ------------------------------------------

def priority_score(
    impact: float, confidence: float, urgency: float, evidence: float, effort: float,
) -> int:
    """Internal 0-100 priority: Impact + Confidence + Urgency + Evidence - Effort.

    All inputs are 0-100. The result ranks WHAT MATTERS, not what is noisy.
    """
    score = impact * 0.30 + confidence * 0.20 + urgency * 0.25 + evidence * 0.15 - effort * 0.10
    return int(round(max(0, min(100, score))))


def normalize_priorities(items: list[dict[str, Any]], max_critical: int = 1, max_high: int = 3) -> list[dict[str, Any]]:
    """PRIORITY NORMALIZATION (audit #13): cap how many items can claim
    CRITICAL / HIGH so the labels keep meaning 'harus segera diperhatikan'."""
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    items = sorted(items, key=lambda x: (order.get(x.get("priority"), 9), -int(x.get("priority_score") or 0)))
    critical_seen = high_seen = 0
    out: list[dict[str, Any]] = []
    for item in items:
        p = item.get("priority", "LOW")
        if p == "CRITICAL":
            if critical_seen < max_critical:
                critical_seen += 1
            else:
                item["priority"] = "HIGH"
                item["normalized"] = True
                p = "HIGH"
        if p == "HIGH":
            if high_seen < max_high:
                high_seen += 1
            else:
                item["priority"] = "MEDIUM"
                item["normalized"] = True
        out.append(item)
    return sorted(out, key=lambda x: (order.get(x.get("priority"), 9), -int(x.get("priority_score") or 0)))


def recommendation_struct(
    what: str, why: str, evidence: str, sample_size: int,
    confidence: dict[str, Any], expected_impact: str, risk: str, next_action: str,
) -> dict[str, Any]:
    """Standard recommendation structure (audit #12):
    WHAT / WHY / EVIDENCE / SAMPLE_SIZE / CONFIDENCE / EXPECTED_IMPACT / RISK / NEXT_ACTION."""
    return {
        "what": what,
        "why": why,
        "evidence": evidence,
        "sample_size": sample_size,
        "confidence": confidence,
        "expected_impact": expected_impact,
        "risk": risk,
        "next_action": next_action,
    }
