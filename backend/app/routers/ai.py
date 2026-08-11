"""AI endpoints: chat, analysis, content plans, generators, tasks."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.decision_engine import compute_video_score
from app.agents.tools import TOOLS, PermissionLevel, execute_tool
from app.auth.deps import get_current_user
from app.database import get_db
from app.models.ai_task import AiTask
from app.models.content_plan_item import ContentPlanItem
from app.models.user import User
from app.models.video import Video
from app.routers.deps import get_user_channel, user_channel_ids
from app.ai.chat import handle_chat
from app.ai.memory import require_channel
from app.ai.service import (
    generate_content_patterns,
    generate_description,
    generate_seo,
    generate_titles,
    run_agent,
)
from app.services.approval_service import create_approval
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.rate_limit import rate_limit
from app.utils.security import check_csrf

router = APIRouter(prefix="/ai", tags=["ai"])
logger = get_logger("ai.routers")

ai_rate = rate_limit(30, 60)


def _task_dict(t: AiTask) -> dict:
    return {
        "id": t.id,
        "channel_id": t.channel_id,
        "task_type": t.task_type,
        "instruction": t.instruction,
        "status": t.status,
        "priority": t.priority,
        "result": t.result,
        "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


class AiChatRequest(BaseModel):
    channel_id: str
    message: str = Field(min_length=1, max_length=4000)


@router.post("/chat")
async def chat(payload: AiChatRequest, request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db), _: None = Depends(ai_rate)) -> dict:
    check_csrf(request)
    require_channel(db, payload.channel_id)
    result = await handle_chat(db, user, payload.channel_id, payload.message)
    return result


class AnalyzeChannelRequest(BaseModel):
    channel_id: str
    instruction: str | None = None


@router.post("/analyze-channel")
async def analyze_channel(payload: AnalyzeChannelRequest, request: Request,
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    instruction = payload.instruction or "Analyze my channel's performance and give recommendations."
    result = await asyncio.to_thread(run_agent, db, user, ch, "channel_analyst", instruction)
    return result


class AnalyzeVideoRequest(BaseModel):
    video_id: str


@router.post("/analyze-video")
async def analyze_video(payload: AnalyzeVideoRequest, request: Request,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ids = user_channel_ids(db, user)
    video = db.get(Video, payload.video_id)
    if video is None or video.channel_id not in ids:
        raise AppError(404, "NOT_FOUND", "Video not found.")
    score = compute_video_score(video)
    ch = video.channel
    result = await asyncio.to_thread(run_agent, db, user, ch, "decision_engine",
                                     f"Analyze video: {video.title}")
    result["score"] = score
    return result


class ContentPlanRequest(BaseModel):
    channel_id: str
    days: int | None = None
    instruction: str | None = None


@router.post("/content-plan")
async def ai_content_plan(payload: ContentPlanRequest, request: Request,
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    instruction = (
        payload.instruction
        or f"Create a content plan for the next {payload.days or 30} days with "
        "10-20 concrete video ideas that fit the channel niche."
    )
    result = await asyncio.to_thread(run_agent, db, user, ch, "content_strategist", instruction)
    # Persist generated items
    saved = []
    for action in result.get("actions", []):
        if action.get("id") in ("create_content_plan", "create_video_draft"):
            items = action.get("payload", {}).get("items", [])
            if not items and action.get("payload", {}).get("title"):
                items = [action["payload"]]
            for idea in items[:30]:
                if not isinstance(idea, dict) or not idea.get("title"):
                    continue
                item = ContentPlanItem(
                    channel_id=ch.id,
                    title=str(idea["title"])[:500],
                    description=idea.get("description"),
                    idea=idea.get("idea"),
                    target_keyword=idea.get("target_keyword"),
                    status="IDEA",
                )
                db.add(item)
                saved.append({"title": item.title, "id": item.id})
    db.commit()
    log_audit(db, user_id=user.id, channel_id=ch.id, action="ai_content_plan",
              target=ch.title, result="ok", metadata={"items_saved": len(saved)})
    return {"summary": result.get("summary", ""), "items": saved}


class ContentPatternsRequest(BaseModel):
    channel_id: str
    days: int = 28


@router.post("/content-patterns")
async def ai_content_patterns(payload: ContentPatternsRequest, request: Request,
                              user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)) -> dict:
    """Analyze proven title patterns (views by content + traffic sources), then
    auto-save 3 title/description recommendations to the content plan as SCHEDULED."""
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    result = await asyncio.to_thread(generate_content_patterns, db, ch, min(max(payload.days, 1), 365))
    log_audit(db, user_id=user.id, channel_id=ch.id, action="ai_content_patterns",
              target=ch.title, result="ok", metadata={"saved": len(result["saved"])})
    return result


class GenerateTitlesRequest(BaseModel):
    video_id: str | None = None
    topic: str | None = None
    channel_id: str | None = None


@router.post("/generate-titles")
async def generate_titles_endpoint(payload: GenerateTitlesRequest, request: Request,
                                   user: User = Depends(get_current_user),
                                   db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = _resolve_channel(db, user, payload.channel_id)
    titles = await asyncio.to_thread(generate_titles, db, ch, payload.topic, payload.video_id)
    return {"titles": titles}


class GenerateDescriptionRequest(BaseModel):
    title: str | None = None
    topic: str | None = None
    channel_id: str | None = None


@router.post("/generate-description")
async def generate_description_endpoint(payload: GenerateDescriptionRequest, request: Request,
                                        user: User = Depends(get_current_user),
                                        db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = _resolve_channel(db, user, payload.channel_id)
    desc = await asyncio.to_thread(generate_description, db, ch, payload.title, payload.topic)
    return {"description": desc}


class GenerateSeoRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    channel_id: str | None = None


@router.post("/generate-seo")
async def generate_seo_endpoint(payload: GenerateSeoRequest, request: Request,
                                user: User = Depends(get_current_user),
                                db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = _resolve_channel(db, user, payload.channel_id)
    return await asyncio.to_thread(generate_seo, db, ch, payload.title, payload.description)


class DailyReportRequest(BaseModel):
    channel_id: str | None = None


@router.post("/daily-report")
async def daily_report(payload: DailyReportRequest, request: Request,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    from app.analytics.engine import compute_range, top_videos
    from app.services.approval_service import create_approval  # noqa: F401
    from app.models.approval_request import ApprovalRequest

    ids = user_channel_ids(db, user)
    channel_id = payload.channel_id if payload.channel_id in ids else (ids[0] if ids else None)
    if not channel_id:
        return {
            "channel_health": "No channel connected.",
            "views_growth": None, "subscriber_growth": None,
            "top_videos": [], "worst_videos": [],
            "opportunities": [], "problems": [],
            "recommended_actions": [],
            "pending_approvals_count": 0,
        }
    ch = get_user_channel(db, user, channel_id)
    stats = compute_range(db, ch.id, "28d")
    pending = db.query(ApprovalRequest).filter_by(channel_id=ch.id, status="pending").count()
    report = {
        "channel_health": f"{ch.title}: {ch.subscriber_count} subscribers, {stats['overview']['views']} views (28d).",
        "views_growth": stats["growth"].get("views_pct"),
        "subscriber_growth": stats["growth"].get("subscribers_pct"),
        "top_videos": top_videos(db, ch.id, limit=5, worst=False),
        "worst_videos": top_videos(db, ch.id, limit=5, worst=True),
        "opportunities": [],
        "problems": [],
        "recommended_actions": [],
        "pending_approvals_count": pending,
    }
    # Best-effort AI enrichment
    try:
        result = await asyncio.to_thread(run_agent, db, user, ch, "analytics_analyst",
                                         "Produce today's channel report.")
        report["opportunities"] = result.get("recommendations", [])[:3]
        report["recommended_actions"] = [
            {"label": a.get("label"), "id": a.get("id"), "requires_approval": a.get("requires_approval", False)}
            for a in result.get("actions", [])[:5]
        ]
    except AppError as exc:
        report["opportunities"] = [f"Enable AI (AI_API_KEY) for deeper analysis. ({exc.code})"]
    log_audit(db, user_id=user.id, channel_id=ch.id, action="daily_report", target=ch.title, result="ok")
    return report


def _resolve_channel(db: Session, user: User, channel_id: str | None = None):
    from app.models.channel import Channel

    ids = user_channel_ids(db, user)
    if not ids:
        raise AppError(404, "NOT_FOUND", "Connect a YouTube channel first.")
    if channel_id:
        if channel_id not in ids:
            raise AppError(404, "NOT_FOUND", "Channel not found.")
        return db.get(Channel, channel_id)
    return db.get(Channel, ids[0])


class ActionExecuteRequest(BaseModel):
    channel_id: str
    action_id: str
    params: dict = {}


@router.post("/actions/execute")
async def execute_action(payload: ActionExecuteRequest, request: Request,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Execute one AI-suggested action. READ/WRITE run immediately; HIGH_RISK
    actions (e.g. reply to a comment) create an approval request first."""
    check_csrf(request)
    channel = get_user_channel(db, user, payload.channel_id)
    tool = TOOLS.get(payload.action_id)
    if tool is None:
        raise AppError(404, "NOT_FOUND", f"Tool '{payload.action_id}' tidak dikenal.")
    if tool.permission is PermissionLevel.HIGH_RISK:
        approval = create_approval(
            db,
            channel_id=channel.id,
            action_type=tool.name,
            target_id=payload.params.get("comment_id") or payload.params.get("video_id"),
            proposed_change=payload.params or {},
            reason="Aksi berisiko tinggi dari AI - butuh persetujuan Anda.",
            risk_level="HIGH",
            user_id=user.id,
        )
        return {"approved": False, "approval_id": approval.id,
                "message": "Aksi berisiko tinggi: menunggu persetujuan Anda di halaman Approvals."}
    try:
        result = await asyncio.to_thread(execute_tool, db, user, channel, payload.action_id, payload.params)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(500, "ACTION_FAILED", f"Aksi gagal dijalankan: {exc}") from exc
    log_audit(db, user_id=user.id, channel_id=channel.id, action="ai_action_executed",
              target=payload.action_id, result="ok", metadata={"params": payload.params})
    return {"approved": True, "result": result}


@router.get("/tasks")
def list_tasks(channel_id: str | None = None, status: str = "",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    q = db.query(AiTask)
    if channel_id:
        q = q.filter(AiTask.channel_id == channel_id)
    if status:
        q = q.filter(AiTask.status == status)
    q = q.order_by(AiTask.created_at.desc()).limit(100)
    tasks = q.all()
    return {"items": [_task_dict(t) for t in tasks], "total": len(tasks)}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    task = db.get(AiTask, task_id)
    if task is None:
        raise AppError(404, "NOT_FOUND", "Task not found.")
    return _task_dict(task)
