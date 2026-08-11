"""Comments: list from YouTube, reply to a comment."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.replied_comment import RepliedComment
from app.models.user import User
from app.models.video import Video
from app.routers.deps import get_user_account, get_user_channel, user_channel_ids
from app.services.youtube_service import YouTubeService, reply_to_comment
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.security import check_csrf

router = APIRouter(prefix="/comments", tags=["comments"])
logger = get_logger("comments")


@router.get("")
async def list_comments(channel_id: str | None = None, video_id: str | None = None,
                        sort: str = "newest", limit: int = 50,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ids = user_channel_ids(db, user)
    channel_ids = [channel_id] if channel_id else ids
    if not channel_ids:
        return {"items": [], "total": 0}

    target_video_id = None
    if video_id:
        video = db.get(Video, video_id)
        if video is None or video.channel_id not in ids:
            raise AppError(404, "NOT_FOUND", "Video not found.")
        target_video_id = video.youtube_video_id

    items: list[dict] = []
    for cid in channel_ids[:1]:  # YouTube commentThreads is per-channel/video
        ch = get_user_channel(db, user, cid)
        account = get_user_account(db, user, cid)
        try:
            service = YouTubeService()
            from app.youtube.client import get_authenticated_client

            client = await asyncio.to_thread(get_authenticated_client, db, account)

            recent = (
                db.query(Video.youtube_video_id)
                .filter(Video.channel_id == ch.id, Video.comment_count > 0)
                .order_by(Video.comment_count.desc())
                .limit(5)
                .all()
            )
            if not recent:  # fallback: no synced comment counts yet
                recent = (
                    db.query(Video.youtube_video_id)
                    .filter(Video.channel_id == ch.id)
                    .order_by(Video.published_at.desc())
                    .limit(5)
                    .all()
                )

            def _fetch():
                return service.get_comments(
                    client, video_id=target_video_id, max_results=limit,
                    video_ids=[r[0] for r in recent],
                )

            comments = await asyncio.to_thread(_fetch)
        except AppError as exc:
            logger.warning("Comment fetch failed: %s", exc.code)
            comments = []
        # enrich with video titles
        yids = {c["video_id"] for c in comments if c["video_id"]}
        titles = {}
        if yids:
            rows = db.query(Video).filter(Video.youtube_video_id.in_(yids)).all()
            titles = {v.youtube_video_id: v.title for v in rows}
        for c in comments:
            c["video_title"] = titles.get(c["video_id"], "")
        items.extend(comments)
    # hide comments that have already been replied to (not deleted from YouTube)
    replied: set[str] = set()
    for cid in channel_ids:
        rows = db.query(RepliedComment.comment_id).filter(RepliedComment.channel_id == cid).all()
        replied.update(r[0] for r in rows)
    visible = [c for c in items if c["id"] not in replied]
    if sort == "oldest":
        visible.sort(key=lambda c: c.get("published_at") or "")
    else:
        visible.sort(key=lambda c: c.get("published_at") or "", reverse=True)
    return {"items": visible[:limit], "total": len(visible), "hidden_count": len(replied)}


class CommentReply(BaseModel):
    text: str


class AiDraftRequest(BaseModel):
    channel_id: str
    comment_text: str
    author: str = ""
    video_title: str = ""


@router.post("/ai-draft")
def ai_draft(payload: AiDraftRequest, request: Request, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)) -> dict:
    """Draft an AI reply for a comment (review before sending)."""
    check_csrf(request)
    channel = get_user_channel(db, user, payload.channel_id)
    from app.ai.service import generate_comment_reply
    from app.services.audit_service import log_audit

    draft = generate_comment_reply(
        db, channel, payload.comment_text, payload.author, payload.video_title
    )
    try:
        log_audit(db, user_id=user.id, channel_id=channel.id, action="comment_ai_draft", result="ok")
    except Exception:  # noqa: BLE001
        pass
    return {"draft": draft}


@router.post("/{comment_id}/reply")
async def reply(comment_id: str, payload: CommentReply, request: Request,
                channel_id: str | None = None, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    if not channel_id:
        raise AppError(422, "VALIDATION_ERROR", "channel_id query parameter is required.")
    account = get_user_account(db, user, channel_id)
    result = await asyncio.to_thread(reply_to_comment, db, account, comment_id, payload.text)
    # mark as replied so it disappears from the list (stays on YouTube)
    channel = get_user_channel(db, user, channel_id)
    db.merge(RepliedComment(comment_id=comment_id, channel_id=channel.id))
    db.commit()
    return {**result, "id": comment_id, "text": payload.text, "hidden": True}
