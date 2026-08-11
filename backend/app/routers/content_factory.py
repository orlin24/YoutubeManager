"""Content Factory + AI CEO endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.channel import Channel
from app.models.content_factory import (ContentBrief, ContentExperiment, ContentGenerationLog,
                                        ContentIdea, ContentPerformance, ContentQueue)
from app.models.user import User
from app.routers.deps import get_user_channel, user_channel_ids
from app.services import ceo_service, content_factory
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.security import check_csrf

router = APIRouter(tags=["content-factory"])


class PipelineRequest(BaseModel):
    channel_id: str
    count: int = 3
    dry_run: bool = False


class IdeasRequest(BaseModel):
    channel_id: str
    count: int = 6


class CalendarRequest(BaseModel):
    channel_id: str
    days: int = 7


class ExperimentRequest(BaseModel):
    channel_id: str
    hypothesis: str
    control: str = ""
    variant: str = ""
    metric: str = "views"
    duration_days: int = 14


@router.post("/content-factory/pipeline")
def run_pipeline(payload: PipelineRequest, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    result = content_factory.run_pipeline(db, ch, count=max(1, min(payload.count, 8)),
                                          dry_run=payload.dry_run)
    log_audit(db, user_id=user.id, channel_id=ch.id, action="content_pipeline",
              target=ch.title, result="ok",
              metadata={"queued": result.get("queued", 0), "dry_run": payload.dry_run})
    return result


@router.post("/content-factory/ideas")
def generate_ideas(payload: IdeasRequest, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    ideas = content_factory.generate_ideas(db, ch, count=max(1, min(payload.count, 12)))
    return {"ideas": ideas}


@router.get("/content-factory/ideas")
def list_ideas(channel_id: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    get_user_channel(db, user, channel_id)
    rows = db.query(ContentIdea).filter_by(channel_id=channel_id).order_by(ContentIdea.created_at.desc()).limit(50).all()
    return {"items": [{"id": i.id, "topic": i.topic, "angle": i.angle, "format": i.format,
                       "reason": i.reason, "confidence": i.confidence, "content_type": i.content_type,
                       "priority": i.priority, "status": i.status} for i in rows]}


def _brief_payload(brief: object) -> dict:
    if brief is None:
        return {}
    tv = brief.title_variants or []
    titles = [t.get("title") for t in tv if isinstance(t, dict) and t.get("title")] or []
    th = brief.thumbnail_variants or {}
    if isinstance(th, dict):
        concept = th.get("concept", "")
        variants = th.get("variants", [])
    else:
        concept, variants = "", []
    outline = brief.script_outline or {}
    keywords = brief.seo_keywords or []
    if isinstance(keywords, dict):  # data lama: {"keywords": [...]}
        keywords = keywords.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = []
    return {
        "title_variants": titles,
        "thumbnail_concept": concept,
        "thumbnail_variants": [v.get("concept") or v.get("image_prompt", "") for v in variants if isinstance(v, dict)][:3],
        "script_title": outline.get("title", ""),
        "script_hook": outline.get("hook", ""),
        "script_outline": outline.get("sections", outline.get("steps", [])),
        "keywords": keywords,
        "hook": brief.hook or "",
        "audience": brief.audience or "",
        "duration": brief.duration or "",
        "quality_score": brief.quality_score,
        "quality_result": brief.quality_result,
    }


@router.get("/content-factory/queue")
def list_queue(channel_id: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    get_user_channel(db, user, channel_id)
    rows = db.query(ContentQueue).filter_by(channel_id=channel_id).order_by(ContentQueue.created_at.desc()).limit(50).all()
    items = []
    for q in rows:
        brief = db.get(ContentBrief, q.brief_id) if q.brief_id else None
        items.append({"id": q.id, "title": q.title, "content_type": q.content_type, "status": q.status,
                      "priority": q.priority, "publish_date": q.publish_date, "notes": q.notes,
                      "brief": _brief_payload(brief)})
    return {"items": items}


@router.post("/content-factory/queue/{queue_id}/advance")
def advance_queue(queue_id: str, request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    """Majukan item Content Queue satu tahap pipeline (atau ke status target)."""
    check_csrf(request)
    item = db.get(ContentQueue, queue_id)
    if item is None:
        raise AppError(404, "NOT_FOUND", "Item queue tidak ditemukan.")
    get_user_channel(db, user, item.channel_id)

    content_factory.advance(db, item)

    log_audit(db, user_id=user.id, channel_id=item.channel_id, action="queue_advance",
              target=(item.title or item.id)[:80], result="ok",
              metadata={"queue_id": item.id, "status": item.status})
    return {"id": item.id, "status": item.status, "publish_date": item.publish_date}


@router.post("/content-factory/calendar")
def calendar(payload: CalendarRequest, request: Request, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    plan = content_factory.build_calendar(db, ch, days=max(1, min(payload.days, 30)))
    return {"plan": plan}


@router.get("/content-factory/experiments")
def list_experiments(channel_id: str, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)) -> dict:
    get_user_channel(db, user, channel_id)
    rows = db.query(ContentExperiment).filter_by(channel_id=channel_id).order_by(ContentExperiment.created_at.desc()).all()
    return {"items": [{"id": e.id, "hypothesis": e.hypothesis, "metric": e.metric, "status": e.status,
                       "result": e.result, "confidence": e.confidence} for e in rows]}


@router.post("/content-factory/experiments")
def create_experiment(payload: ExperimentRequest, request: Request,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    get_user_channel(db, user, payload.channel_id)
    exp = content_factory.create_experiment(db, payload.channel_id, payload.hypothesis,
                                            payload.control, payload.variant,
                                            payload.metric, payload.duration_days)
    return {"id": exp.id, "status": exp.status}


@router.get("/content-factory/providers")
def providers(user: User = Depends(get_current_user)) -> dict:
    return content_factory.provider_status()


@router.get("/content-factory/logs")
def gen_logs(channel_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    get_user_channel(db, user, channel_id)
    rows = db.query(ContentGenerationLog).filter_by(channel_id=channel_id).order_by(ContentGenerationLog.created_at.desc()).limit(30).all()
    return {"items": [{"component": r.component, "status": r.status, "latency_ms": r.latency_ms,
                       "created_at": r.created_at, "error": r.error} for r in rows]}


# ---- AI CEO -----------------------------------------------------------------


@router.get("/ceo/overview")
def ceo_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return ceo_service.ceo_overview(db, ids)


@router.get("/ceo/priorities")
def ceo_priorities(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return {"items": ceo_service.today_priorities(db, ids)}


@router.get("/ceo/opportunities")
def ceo_opportunities(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return {"items": ceo_service.opportunities(db, ids)}


@router.get("/ceo/risks")
def ceo_risks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return {"items": ceo_service.risks(db, ids)}


@router.get("/ceo/recommendation")
def ceo_recommendation(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return ceo_service.recommendation(db, ids)


@router.get("/ceo/allocation")
def ceo_allocation(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return {"items": ceo_service.allocation(db, ids)}


@router.get("/ceo/scorecard")
def ceo_scorecard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    return ceo_service.scorecard(db, ids)


@router.post("/ceo/telegram")
def ceo_telegram(request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ids = user_channel_ids(db, user)
    text = ceo_service.telegram_ceo_report(db, ids)
    if not text:
        raise AppError(502, "TELEGRAM_FAILED", "Gagal mengirim laporan CEO (Telegram belum dikonfigurasi?).")
    log_audit(db, user_id=user.id, action="ceo_report_sent", result="ok")
    return {"success": True, "message": "Laporan CEO terkirim ke Telegram."}
