"""Autonomous AI employee: status, mode control, kill switch, task review."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.ai_task import AiTask
from app.models.user import User
from app.routers.deps import user_channel_ids
from app.services import autonomous_service
from app.services.audit_service import log_audit
from app.utils.security import check_csrf

router = APIRouter(prefix="/ai", tags=["autonomous"])


class ModeRequest(BaseModel):
    mode: str


class DryRunRequest(BaseModel):
    dry_run: bool


@router.get("/autonomous/status")
def auto_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return autonomous_service.status(db)


@router.post("/autonomous/mode")
def set_mode(payload: ModeRequest, request: Request, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    mode = payload.mode.strip().upper()
    if mode not in autonomous_service.MODES:
        from app.utils.errors import AppError

        raise AppError(422, "VALIDATION_ERROR", "Mode harus OFF/RECOMMEND_ONLY/SEMI_AUTO/FULL_AUTO.")
    autonomous_service.set_autonomous_setting(db, "mode", mode)
    # mode OFF = mati; mode lain = aktif (meng-allow-enable dari web tanpa .env)
    autonomous_service.set_autonomous_setting(db, "enabled", mode != "OFF")
    log_audit(db, user_id=user.id, action="ai_mode_changed", target=mode, result="ok")
    return {"success": True, "mode": mode}


@router.post("/autonomous/dry-run")
def set_dry_run(payload: DryRunRequest, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    autonomous_service.set_autonomous_setting(db, "dry_run", bool(payload.dry_run))
    log_audit(db, user_id=user.id, action="ai_dry_run_changed",
              target="on" if payload.dry_run else "off", result="ok")
    return {"success": True, "dry_run": bool(payload.dry_run)}


@router.post("/autonomous/run-now")
def run_now(request: Request, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    """Run one autonomous cycle immediately (manual trigger)."""
    check_csrf(request)
    result = autonomous_service.run_cycle(db)
    log_audit(db, user_id=user.id, action="ai_auto_cycle", result="ok",
              metadata={"manual": True, "status": result.get("status")})
    return result


@router.post("/emergency-stop")
def emergency_stop(request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    result = autonomous_service.emergency_stop(db)
    log_audit(db, user_id=user.id, action="ai_emergency_stop", result="ok")
    return result


@router.post("/emergency-resume")
def emergency_resume(request: Request, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    result = autonomous_service.resume(db)
    log_audit(db, user_id=user.id, action="ai_emergency_resume", result="ok")
    return result


@router.get("/autonomous/tasks")
def auto_tasks(status: str = "", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    q = db.query(AiTask).filter(AiTask.channel_id.in_(ids)) if ids else db.query(AiTask).filter(AiTask.id.is_(None))
    # default: sembunyikan yang di-cancel & report rutin supaya daftar fokus pada tugas otomatis
    q = q.filter(AiTask.status != "cancelled")
    if status:
        q = q.filter(AiTask.status == status)
    else:
        q = q.filter(AiTask.task_type != "daily_report")
    rows = q.order_by(AiTask.priority.desc(), AiTask.created_at.desc()).limit(60).all()
    return {"items": [
        {"id": t.id, "channel_id": t.channel_id, "task_type": t.task_type,
         "instruction": t.instruction, "priority": t.priority, "risk_level": t.risk_level,
         "status": t.status, "error": t.error, "created_at": t.created_at,
         "completed_at": t.completed_at}
        for t in rows
    ]}
