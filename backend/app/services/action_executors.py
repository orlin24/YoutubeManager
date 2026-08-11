"""Executors for approved HIGH_RISK actions.

Registered at startup so that when the user approves an AI-suggested action on
the Approvals page, it actually runs against YouTube.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.approval_request import ApprovalRequest
from app.models.channel import Channel
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services.approval_service import register_executor
from app.services.youtube_service import reply_to_comment, update_video_metadata
from app.utils.errors import AppError
from app.utils.logging import get_logger

logger = get_logger("executors")


def _account_for(db: Session, approval: ApprovalRequest) -> YouTubeAccount:
    channel = db.get(Channel, approval.channel_id)
    if channel is None or channel.youtube_account is None:
        raise AppError(404, "NOT_FOUND", "YouTube account tidak ditemukan untuk channel ini.")
    return channel.youtube_account


def _reply_comment_executor(db: Session, approval: ApprovalRequest) -> dict:
    change = approval.proposed_change or {}
    comment_id = change.get("comment_id") or approval.target_id
    text = change.get("text", "")
    if not comment_id or not text:
        raise AppError(400, "VALIDATION_ERROR", "comment_id dan text diperlukan.")
    account = _account_for(db, approval)
    result = reply_to_comment(db, account, comment_id, text)
    logger.info("Replied to comment %s via approval %s", comment_id, approval.id)
    return {"replied_comment_id": comment_id, **result}


def _update_metadata_executor(db: Session, approval: ApprovalRequest) -> dict:
    change = approval.proposed_change or {}
    video_id = change.get("video_id") or approval.target_id
    video = db.get(Video, video_id) if video_id else None
    if video is None:
        raise AppError(404, "NOT_FOUND", "Video tidak ditemukan.")
    account = _account_for(db, approval)
    fields = {k: v for k, v in change.items() if k in ("title", "description", "tags") and v is not None}
    if not fields:
        raise AppError(400, "VALIDATION_ERROR", "Tidak ada field metadata yang diubah.")
    result = update_video_metadata(db, account, video, **fields)
    logger.info("Updated metadata for video %s via approval %s", video_id, approval.id)
    return {"video_id": video_id, "fields": list(fields), **result}






# ---- autonomous AI task executors (approval-gated) -------------------------


def _autonomous_task_executor(db: Session, approval: ApprovalRequest) -> dict:
    """Run an AI task once the user approves it (from the autonomous loop)."""
    from app.models.ai_task import AiTask
    from app.models.channel import Channel
    from app.services import autonomous_service

    change = approval.proposed_change or {}
    task_id = change.get("task_id") or change.get("instruction")
    task = db.get(AiTask, task_id) if isinstance(task_id, str) and len(task_id) > 20 else None
    if task is None:
        # fall back: find by instruction text
        task = (
            db.query(AiTask)
            .filter(AiTask.channel_id == approval.channel_id,
                    AiTask.instruction == change.get("instruction"),
                    AiTask.status == "waiting_approval")
            .order_by(AiTask.created_at.desc())
            .first()
        )
    if task is None:
        raise AppError(404, "NOT_FOUND", "Task AI tidak ditemukan.")
    channel = db.get(Channel, task.channel_id)
    if channel is None:
        raise AppError(404, "NOT_FOUND", "Channel tidak ditemukan.")
    if task.status != "waiting_approval":
        task.status = "running"
        db.commit()
    result = autonomous_service._execute_task(db, task, channel, dry_run=False)
    logger.info("Autonomous task %s executed via approval %s", task.id, approval.id)
    return result


def _register() -> None:
    register_executor("reply_comment", _reply_comment_executor)
    register_executor("update_video_metadata", _update_metadata_executor)
    for t in ("analyze", "content_pattern", "duplicate_titles", "anomaly_alert"):
        register_executor(t, _autonomous_task_executor)
    logger.info("Registered %d action executor(s)", 6)
