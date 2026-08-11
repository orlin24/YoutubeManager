"""Business Intelligence endpoints: forecasts, risks, opportunities, simulation,
optimization, strategy, accuracy. Read the cached snapshot (no heavy work per refresh)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.bi import ForecastHistory
from app.models.user import User
from app.routers.deps import user_channel_ids
from app.services import bi_engine
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.security import check_csrf

router = APIRouter(prefix="/bi", tags=["bi"])


class SimulateRequest(BaseModel):
    name: str = "Simulasi"
    uploads_per_week: float | None = None
    capacity_shift_pct: float = 0.0
    elasticity: float = 0.6


class OptimizeRequest(BaseModel):
    max_videos_per_day: float = 4.0


@router.get("/overview")
def bi_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    snap = bi_engine.get_snapshot(db)
    return {
        "generated_at": snap.get("generated_at"),
        "per_channel": snap.get("per_channel", []),
        "risks": snap.get("risks", []),
        "opportunities": snap.get("opportunities", []),
        "allocation": snap.get("allocation", {}),
    }


@router.post("/refresh")
def bi_refresh(request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    snap = bi_engine.compute_snapshot(db)
    log_audit(db, user_id=user.id, action="bi_refreshed", result="ok")
    return {"success": True, "generated_at": snap.get("generated_at")}


@router.get("/forecasts")
def bi_forecasts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    snap = bi_engine.get_snapshot(db)
    items = [c for c in snap.get("per_channel", []) if c["channel_id"] in ids] if ids else snap.get("per_channel", [])
    return {"items": [{"channel_id": c["channel_id"], "title": c["title"], "mode": c["mode"],
                       "class": c.get("class"), "views_forecast": c.get("views_forecast"),
                       "subs_forecast": c.get("subs_forecast"),
                       "revenue_forecast": c.get("revenue_forecast")} for c in items]}


@router.get("/risks")
def bi_risks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    snap = bi_engine.get_snapshot(db)
    return {"items": snap.get("risks", [])}


@router.get("/opportunities")
def bi_opportunities(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    snap = bi_engine.get_snapshot(db)
    return {"items": snap.get("opportunities", [])}


@router.post("/simulate")
def bi_simulate(payload: SimulateRequest, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ids = user_channel_ids(db, user)
    # portfolio state from snapshot (views/upload elasticity)
    snap = bi_engine.get_snapshot(db)
    state = {"uploads_per_week": 1, "views_per_upload": 0}
    for c in snap.get("per_channel", []):
        state["views_per_upload"] += (c.get("views_forecast") or {}).get("current", 0) or 0
    result = bi_engine.simulate(payload.model_dump(), state)
    log_audit(db, user_id=user.id, action="bi_simulated", result="ok", metadata={"name": payload.name})
    return result


@router.get("/optimize")
def bi_optimize(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    snap = bi_engine.get_snapshot(db)
    return snap.get("allocation", bi_engine.optimize(db, ids, {"max_videos_per_day": 4}))


@router.post("/optimize")
def bi_optimize_with_constraints(payload: OptimizeRequest, request: Request,
                                 user: User = Depends(get_current_user),
                                 db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ids = user_channel_ids(db, user)
    return bi_engine.optimize(db, ids, {"max_videos_per_day": payload.max_videos_per_day})


@router.get("/strategy")
def bi_strategy(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"items": bi_engine.strategic_answers(db)}


@router.get("/forecast-history")
def bi_forecast_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.query(ForecastHistory).order_by(ForecastHistory.forecast_date.desc()).limit(40).all()
    return {"items": [{"metric": r.metric, "forecast_date": r.forecast_date, "target_date": r.target_date,
                       "predicted_value": r.predicted_value, "lower_bound": r.lower_bound,
                       "upper_bound": r.upper_bound, "confidence": r.confidence,
                       "actual_value": r.actual_value, "error": r.error,
                       "model_version": r.model_version} for r in rows]}


@router.get("/accuracy")
def bi_accuracy(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return bi_engine.forecast_accuracy(db)
