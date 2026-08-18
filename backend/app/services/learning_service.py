"""Automatic Learning service.

The loop (audit DoD): DATA -> EVIDENCE -> DECISION -> RECOMMENDATION ->
ACTUAL RESULT -> COMPARE -> LEARN -> UPDATE CONFIDENCE -> UPDATE MEMORY ->
CHANGE FUTURE RECOMMENDATION.

Every AI recommendation is recorded (recommendation_id), then after the
evaluation period its EXPECTED vs ACTUAL outcome is compared. Success raises
pattern confidence, failure lowers it, and the memory is injected back into
the AI context so it actually changes the next decision (audit #18).

No automatic destructive action is ever taken here (audit #28).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.learning import LearningMemory, RecommendationOutcome
from app.services.audit_service import log_audit
from app.services.confidence_engine import decay_confidence, level_from_score
from app.utils.logging import get_logger

logger = get_logger("learning")

EVAL_PERIOD_DAYS = 7  # after this long a pending recommendation is evaluated
SUCCESS_FACTOR = 1.0  # actual >= expected*1.0 -> success
FAILURE_FACTOR = 0.6  # actual < expected*0.6 -> failure


def _naive(dt: datetime | None) -> datetime | None:
    """SQLite (Pi) stores/returns naive datetimes; Postgres (dev) returns aware.
    Normalize before any Python-side datetime arithmetic."""
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _utcnow() -> datetime:
    """Naive-UTC now, safe to subtract from DB datetimes on both DBs."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_recommendation(
    db: Session,
    channel_id: str,
    decision: str,
    reason: str = "",
    evidence: str = "",
    sample_size: int = 0,
    confidence: str = "INSUFFICIENT_DATA",
    expected_outcome: str = "",
    expected_value: float | None = None,
) -> RecommendationOutcome:
    """Persist a recommendation so expected vs actual can be compared later."""
    row = RecommendationOutcome(
        channel_id=channel_id,
        decision=decision[:600],
        reason=reason,
        evidence=evidence,
        sample_size=sample_size,
        confidence=confidence,
        expected_outcome=expected_outcome[:300],
        expected_value=expected_value,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _recent_actual_views(db: Session, channel_id: str, since: datetime) -> float | None:
    """Median view count of videos published after `since` (actual result of
    following the recommendation). None when there is no new video yet."""
    from app.models.video import Video

    rows = (
        db.query(Video.view_count)
        .filter(Video.channel_id == channel_id, Video.published_at >= _naive(since))
        .all()
    )
    values = sorted(v for (v,) in rows if v is not None)
    if not values:
        return None
    n = len(values)
    mid = n // 2
    return float(values[mid]) if n % 2 else (values[mid - 1] + values[mid]) / 2.0


def _update_pattern_memory(
    db: Session, channel_id: str, pattern: str, outcome: RecommendationOutcome,
    actual: float, success: bool,
) -> None:
    """Update or create the WINNING/FAILED pattern memory for this channel and
    write a CONFIDENCE_HISTORY entry. Historical evidence is never deleted."""
    from app.models.video import Video

    kind = "WINNING_PATTERN" if success else "FAILED_PATTERN"
    # baseline = performa channel SEBELUM rekomendasi (hindari kontaminasi hasil)
    baseline = (
        db.query(Video.view_count)
        .filter(Video.channel_id == channel_id, Video.published_at < _naive(outcome.created_at))
        .all()
    )
    base_values = sorted(v for (v,) in baseline if v is not None)
    median_base = (
        base_values[len(base_values) // 2]
        if base_values and len(base_values) % 2
        else ((base_values[len(base_values) // 2 - 1] + base_values[len(base_values) // 2]) / 2.0 if len(base_values) >= 2 else (base_values[0] if base_values else 0))
    )
    performance = f"{actual / median_base:.1f}x median channel" if median_base else "n/a"

    existing = (
        db.query(LearningMemory)
        .filter(
            LearningMemory.channel_id == channel_id,
            LearningMemory.pattern == pattern,
            LearningMemory.kind.in_(("WINNING_PATTERN", "FAILED_PATTERN")),
        )
        .order_by(LearningMemory.updated_at.desc())
        .first()
    )
    before_conf = outcome.confidence
    if existing:
        # keep old evidence: append, never delete
        old_evidence = existing.evidence or ""
        existing.evidence = f"{old_evidence} | {outcome.evidence or outcome.decision}"[:2000]
        existing.sample_size += outcome.sample_size or 1
        existing.performance = performance
        existing.kind = kind
        existing.updated_at = _utcnow()
        new_conf = existing.confidence
        if success:
            new_conf = min(95.0, existing.confidence + 8 + (outcome.sample_size or 1) * 2)
        else:
            new_conf = max(0.0, existing.confidence - 12)
        existing.confidence = new_conf
        existing.data = {
            **(existing.data or {}),
            "history": (existing.data or {}).get("history", []) + [
                {"at": _utcnow().isoformat(), "actual": actual,
                 "success": success, "confidence_before": before_conf, "confidence_after": round(new_conf, 1)}
            ],
        }
        memory = existing
    else:
        memory = LearningMemory(
            channel_id=channel_id,
            kind=kind,
            pattern=pattern[:300],
            evidence=outcome.evidence or outcome.decision,
            sample_size=outcome.sample_size or 1,
            confidence=35.0 if success else 15.0,
            performance=performance,
            data={"history": [{"at": _utcnow().isoformat(), "actual": actual,
                              "success": success, "confidence_before": before_conf,
                              "confidence_after": 35.0 if success else 15.0}]},
        )
        new_conf = memory.confidence
        db.add(memory)

    db.add(LearningMemory(
        channel_id=channel_id,
        kind="CONFIDENCE_HISTORY",
        pattern=pattern[:300],
        evidence=outcome.decision,
        sample_size=outcome.sample_size or 1,
        confidence=new_conf,
        performance=f"{before_conf} -> {round(new_conf, 1)} ({'naik' if success else 'turun'})",
        data={"outcome_id": outcome.id, "success": success, "actual": actual},
    ))
    db.commit()


def evaluate_outcomes(db: Session, eval_days: int = EVAL_PERIOD_DAYS) -> dict:
    """Compare EXPECTED vs ACTUAL for pending recommendations, then update
    pattern confidence + memory + audit log. Runs automatically (scheduler)."""
    from app.models.channel import Channel
    from app.models.learning import LearningMemory

    now = _utcnow()
    cutoff = now - timedelta(days=eval_days)
    pending = (
        db.query(RecommendationOutcome)
        .filter(RecommendationOutcome.status == "pending", RecommendationOutcome.created_at <= cutoff)
        .order_by(RecommendationOutcome.created_at.asc())
        .all()
    )
    evaluated = updated = 0
    for out in pending:
        actual = _recent_actual_views(db, out.channel_id, out.created_at)
        if actual is None:
            # no new video yet; keep waiting but do not block forever
            if (now - (_naive(out.created_at) or now)).days > eval_days * 3:
                out.status = "evaluated"
                out.actual_outcome = "Tidak ada data hasil (belum ada video baru)."
                out.evaluated_at = now
                db.commit()
                evaluated += 1
            continue
        expected = out.expected_value if out.expected_value else 0.0
        if expected <= 0:
            success = False
        elif actual >= expected * SUCCESS_FACTOR:
            success = True
        elif actual < expected * FAILURE_FACTOR:
            success = False
        else:
            success = None  # neutral

        out.status = "evaluated"
        out.actual_value = actual
        out.evaluated_at = now
        if success is True:
            out.actual_outcome = f"Hasil {actual:.0f} views, memenuhi target ({expected:.0f})."
        elif success is False:
            out.actual_outcome = f"Hasil {actual:.0f} views, di bawah target ({expected:.0f})."
        else:
            out.actual_outcome = f"Hasil {actual:.0f} views, mendekati target ({expected:.0f})."

        pattern = out.decision
        if success is not None:
            _update_pattern_memory(db, out.channel_id, pattern, out, actual, success)
            updated += 1
            conf_before = out.confidence
            mem = (
                db.query(LearningMemory)
                .filter(
                    LearningMemory.channel_id == out.channel_id,
                    LearningMemory.pattern == pattern,
                    LearningMemory.kind.in_(("WINNING_PATTERN", "FAILED_PATTERN")),
                )
                .order_by(LearningMemory.updated_at.desc())
                .first()
            )
            conf_after = f"{mem.confidence:.0f}" if mem else conf_before
            channel = db.get(Channel, out.channel_id)
            log_audit(
                db, user_id=None, action="ai_learning",
                target=channel.channel_id if channel else out.channel_id,
                result="ok",
                metadata={
                    "decision_id": out.id, "recommendation": out.decision,
                    "confidence_before": conf_before, "confidence_after": conf_after,
                    "evidence": out.evidence, "reason": out.actual_outcome,
                    "success": success,
                },
            )
        db.commit()
        evaluated += 1

    if updated:
        try:
            _apply_decay_to_patterns(db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pattern decay failed: %s", exc)
        bump_strategy_version(db, reason=f"Evaluasi {updated} rekomendasi")
    return {"evaluated": evaluated, "updated": updated, "pending_left": len(pending) - evaluated}


def _apply_decay_to_patterns(db: Session) -> None:
    """Confidence decay (audit #19): patterns that stop being reconfirmed lose
    confidence over time (HIGH -> MEDIUM -> LOW), but evidence is kept."""
    from app.models.channel import Channel

    now = _utcnow()
    rows = (
        db.query(LearningMemory)
        .filter(LearningMemory.kind.in_(("WINNING_PATTERN", "EXPERIMENT_RESULT")))
        .all()
    )
    for m in rows:
        last_ts = _naive(m.updated_at) or _naive(m.created_at) or now
        age = (now - last_ts).days
        if age <= 14:
            continue
        new = decay_confidence(m.confidence, age)
        if new != m.confidence:
            m.confidence = new
            m.performance = f"{m.performance} (confidence decay: {age} hari tanpa konfirmasi)"
            db.add(LearningMemory(
                channel_id=m.channel_id, kind="CONFIDENCE_HISTORY", pattern=m.pattern,
                evidence="confidence decay", sample_size=m.sample_size, confidence=new,
                performance=f"decay {age} hari",
            ))
    db.commit()


def bump_strategy_version(db: Session, reason: str = "update") -> int:
    """STRATEGY_HISTORY: increment the channel-agnostic strategy version."""
    last = (
        db.query(LearningMemory)
        .filter(LearningMemory.kind == "STRATEGY_HISTORY")
        .order_by(LearningMemory.created_at.desc())
        .first()
    )
    version = (last.data or {}).get("version", 0) if last else 0
    version += 1
    db.add(LearningMemory(
        channel_id="__portfolio__",
        kind="STRATEGY_HISTORY",
        pattern=f"Strategi v{version}",
        evidence=reason,
        sample_size=0,
        confidence=float(version),
        performance=reason,
        data={"version": version, "reason": reason},
    ))
    db.commit()
    return version


def get_strategy_version(db: Session) -> int:
    last = (
        db.query(LearningMemory)
        .filter(LearningMemory.kind == "STRATEGY_HISTORY")
        .order_by(LearningMemory.created_at.desc())
        .first()
    )
    return (last.data or {}).get("version", 0) if last else 0


def get_memory_context(db: Session, channel_id: str) -> dict:
    """Memory block injected into AI context (audit #18): winning patterns,
    failed patterns, recent experiments, current strategy, confidence history.
    Memory therefore changes future recommendations."""
    now = datetime.now(timezone.utc)

    def _rows(kind: str, limit: int = 5) -> list[dict]:
        rows = (
            db.query(LearningMemory)
            .filter(LearningMemory.channel_id == channel_id, LearningMemory.kind == kind)
            .order_by(LearningMemory.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"pattern": r.pattern, "evidence": r.evidence, "sample_size": r.sample_size,
             "confidence": round(r.confidence, 1), "performance": r.performance}
            for r in rows
        ]

    winning = _rows("WINNING_PATTERN")
    failed = _rows("FAILED_PATTERN")
    experiments = _rows("EXPERIMENT_RESULT")
    conf_history = _rows("CONFIDENCE_HISTORY", limit=3)
    strategy = get_strategy_version(db)

    if not (winning or failed or experiments):
        return {
            "has_memory": False,
            "strategy_version": strategy,
            "note": "Belum ada memori pembelajaran untuk channel ini.",
        }
    return {
        "has_memory": True,
        "winning_patterns": winning,
        "failed_patterns": failed,
        "recent_experiments": experiments,
        "confidence_history": conf_history,
        "strategy_version": strategy,
        "last_learned": now.isoformat(),
    }


def learning_stats(db: Session, channel_ids: list[str] | None = None) -> dict:
    """Numbers for the 'AI Learning' dashboard (audit #25)."""
    from app.models.channel import Channel
    from app.models.content_factory import ContentExperiment
    from app.models.video import Video

    q = db.query(LearningMemory)
    if channel_ids:
        q = q.filter(LearningMemory.channel_id.in_(channel_ids))
    mem = q.all()

    proven = [m for m in mem if m.kind == "WINNING_PATTERN"]
    failed = [m for m in mem if m.kind == "FAILED_PATTERN"]
    experiments = [m for m in mem if m.kind == "EXPERIMENT_RESULT"]
    insights = [m for m in mem if m.kind == "DECISION_OUTCOME"]

    cq = db.query(ContentExperiment)
    if channel_ids:
        cq = cq.filter(ContentExperiment.channel_id.in_(channel_ids))
    active_experiments = sum(1 for e in cq.all() if getattr(e, "status", "active") not in ("completed", "failed"))

    vq = db.query(Video).count() if not channel_ids else db.query(Video).filter(Video.channel_id.in_(channel_ids)).count()

    last_learned = max((m.updated_at for m in mem), default=None)
    return {
        "videos_analyzed": vq,
        "proven_patterns": len(proven),
        "testing_patterns": len(experiments),
        "failed_patterns": len(failed),
        "active_experiments": active_experiments,
        "new_insights": len(insights),
        "strategy_version": get_strategy_version(db),
        "last_learned": last_learned,
        "recent_memory": [
            {"kind": m.kind, "pattern": m.pattern, "confidence": round(m.confidence, 1),
             "performance": m.performance, "updated_at": m.updated_at}
            for m in sorted(mem, key=lambda x: x.updated_at or x.created_at, reverse=True)[:10]
        ],
    }


def record_experiment_result(
    db: Session, channel_id: str, pattern: str, evidence: str,
    sample_size: int, performance: str, confidence: float,
) -> None:
    """EXPERIMENT_RESULT memory entry (audit #20: PROVEN/PROMISING/INCONCLUSIVE
    state is derived from sample_size + confidence at read time)."""
    db.add(LearningMemory(
        channel_id=channel_id, kind="EXPERIMENT_RESULT", pattern=pattern[:300],
        evidence=evidence, sample_size=sample_size, confidence=confidence, performance=performance,
        data={"status": "PROMISING" if sample_size >= 3 else "INCONCLUSIVE"},
    ))
    db.commit()


def experiment_status(sample_size: int, confidence: float) -> str:
    """PROVEN / PROMISING / INCONCLUSIVE / FAILED (audit #20)."""
    if sample_size >= 10 and confidence >= 55:
        return "PROVEN"
    if sample_size >= 3 and confidence >= 30:
        return "PROMISING"
    if sample_size >= 10 and confidence < 20:
        return "FAILED"
    return "INCONCLUSIVE"
