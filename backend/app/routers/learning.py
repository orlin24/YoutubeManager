"""Automatic Learning dashboard + evaluation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import learning_service

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """AI Learning dashboard numbers (audit #25)."""
    return learning_service.learning_stats(db, channel_ids=None)


@router.get("/memory")
def memory(db: Session = Depends(get_db)):
    """Learning memory: winning/failed patterns + experiments + strategy."""
    rows = (
        db.query(learning_service.LearningMemory)
        .order_by(learning_service.LearningMemory.updated_at.desc())
        .limit(100)
        .all()
    )
    return [
        {"id": r.id, "channel_id": r.channel_id, "kind": r.kind, "pattern": r.pattern,
         "evidence": r.evidence, "sample_size": r.sample_size, "confidence": r.confidence,
         "performance": r.performance, "data": r.data,
         "updated_at": r.updated_at.isoformat() if r.updated_at else None}
        for r in rows
    ]


@router.get("/outcomes")
def outcomes(db: Session = Depends(get_db)):
    """Recommendation history: expected vs actual (audit #16)."""
    rows = (
        db.query(learning_service.RecommendationOutcome)
        .order_by(learning_service.RecommendationOutcome.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {"id": r.id, "channel_id": r.channel_id, "decision": r.decision, "reason": r.reason,
         "evidence": r.evidence, "sample_size": r.sample_size, "confidence": r.confidence,
         "expected_outcome": r.expected_outcome, "expected_value": r.expected_value,
         "status": r.status, "actual_value": r.actual_value, "actual_outcome": r.actual_outcome,
         "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


@router.post("/evaluate")
def evaluate(db: Session = Depends(get_db)):
    """Manually trigger expected-vs-actual comparison (also runs automatically)."""
    return learning_service.evaluate_outcomes(db)
