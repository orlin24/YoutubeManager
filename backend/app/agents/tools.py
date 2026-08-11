"""AI tool allowlist. Tools are the ONLY way the AI touches data/actions.

READ tools query. WRITE tools create drafts/plans. HIGH_RISK tools always route
through the approval system - they never execute directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agents.permissions import PermissionGate, PermissionLevel
from app.models.channel import Channel
from app.models.user import User
from app.models.video import Video
from app.utils.errors import AppError

Handler = Callable[[Session, User, Channel, dict], dict]


@dataclass
class Tool:
    name: str
    description: str
    permission: PermissionLevel
    handler: Handler


def _channel_stats(db: Session, user: User, channel: Channel, params: dict) -> dict:
    return {
        "title": channel.title,
        "subscribers": channel.subscriber_count,
        "total_views": channel.view_count,
        "video_count": channel.video_count,
        "description": channel.description[:500],
        "thumbnail": channel.thumbnail_url,
    }


def _channel_videos(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.models.video import Video

    limit = min(int(params.get("limit", 10)), 50)
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel.id)
        .order_by(Video.published_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "youtube_video_id": v.youtube_video_id,
                "title": v.title,
                "views": v.view_count,
                "likes": v.like_count,
                "comments": v.comment_count,
                "ctr": v.ctr,
                "ai_score": v.ai_score,
                "privacy_status": v.privacy_status,
            }
            for v in videos
        ]
    }


def _video_analytics(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.analytics.engine import compute_range
    from app.models.video import Video

    yid = params.get("video_id") or params.get("youtube_video_id")
    if not yid:
        raise AppError(400, "VALIDATION_ERROR", "video_id is required.")
    video = db.query(Video).filter_by(channel_id=channel.id, youtube_video_id=yid).first()
    if video is None:
        raise AppError(404, "NOT_FOUND", "Video not found.")
    snap = compute_range(db, channel.id, "28d", video_id=video.id)
    return {"video": video.title, "overview": snap["overview"]}


def _channel_analytics(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.analytics.engine import compute_range, top_videos

    result = compute_range(db, channel.id, "28d")
    result["top_videos"] = top_videos(db, channel.id, limit=5)
    return result


def _search_videos(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.models.video import Video

    q = params.get("query", "")
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel.id, Video.title.ilike(f"%{q}%"))
        .order_by(Video.view_count.desc())
        .limit(10)
        .all()
    )
    return {
        "items": [
            {
                "youtube_video_id": v.youtube_video_id,
                "title": v.title,
                "views": v.view_count,
                "privacy_status": v.privacy_status,
            }
            for v in videos
        ]
    }


def _get_comments(db: Session, user: User, channel: Channel, params: dict) -> dict:
    """Live comments fetched from YouTube via the connected OAuth account."""
    from app.models.youtube_account import YouTubeAccount
    from app.services.youtube_service import YouTubeService
    from app.youtube.client import get_authenticated_client

    account = db.get(YouTubeAccount, channel.youtube_account_id)
    if account is None:
        return {"note": "No connected YouTube account for this channel.", "items": []}
    video_yid = params.get("video_id") or params.get("youtube_video_id")
    limit = min(int(params.get("limit", 20)), 50)
    recent = (
        db.query(Video.youtube_video_id)
        .filter(Video.channel_id == channel.id, Video.comment_count > 0)
        .order_by(Video.comment_count.desc())
        .limit(5)
        .all()
    )
    if not recent:  # fallback: no synced comment counts yet
        recent = (
            db.query(Video.youtube_video_id)
            .filter(Video.channel_id == channel.id)
            .order_by(Video.published_at.desc())
            .limit(5)
            .all()
        )
    try:
        client = get_authenticated_client(db, account)
        items = YouTubeService().get_comments(
            client, video_id=video_yid, max_results=limit, video_ids=[r[0] for r in recent]
        )
    except Exception as exc:  # noqa: BLE001 - token expired / offline etc.
        return {"note": f"Komentar tidak bisa diambil dari YouTube: {exc}", "items": []}
    _enrich_comment_titles(db, items)
    from app.models.replied_comment import RepliedComment

    replied = {
        r[0]
        for r in db.query(RepliedComment.comment_id)
        .filter(RepliedComment.channel_id == channel.id)
        .all()
    }
    items = [c for c in items if c["id"] not in replied]
    return {"items": items, "note": f"{len(items)} komentar diambil langsung dari YouTube (yang sudah dibalas disembunyikan)."}


def _enrich_comment_titles(db: Session, items: list[dict]) -> None:
    """Attach the internal video title to each live comment."""
    yids = {c.get("video_id") for c in items if c.get("video_id")}
    if not yids:
        return
    from app.models.video import Video

    titles = {
        v.youtube_video_id: v.title
        for v in db.query(Video).filter(Video.youtube_video_id.in_(yids)).all()
    }
    for c in items:
        c["video_title"] = titles.get(c.get("video_id"), "")


def _reply_comment(db: Session, user: User, channel: Channel, params: dict) -> dict:
    """Propose a reply to a comment. HIGH_RISK: executes only after approval."""
    comment_id = params.get("comment_id")
    text = (params.get("text") or "").strip()
    if not comment_id or not text:
        raise AppError(400, "VALIDATION_ERROR", "comment_id and text are required.")
    return {
        "requires_confirmation": True,
        "message": "Balasan komentar dikirim ke YouTube setelah Anda menyetujui.",
        "proposed": {"comment_id": comment_id, "text": text},
    }


def _create_video_draft(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.models.content_plan_item import ContentPlanItem

    title = params.get("title") or params.get("idea", "Untitled idea")
    item = ContentPlanItem(
        channel_id=channel.id,
        title=title,
        description=params.get("description"),
        idea=params.get("idea"),
        target_keyword=params.get("target_keyword"),
        status="IDEA",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"draft_id": item.id, "title": item.title, "status": item.status}


def _update_video_metadata(db: Session, user: User, channel: Channel, params: dict) -> dict:
    # WRITE on our own data: creates a draft proposal (needs human confirmation
    # because it pushes to YouTube). We route through approval only for
    # HIGH_RISK; metadata edits are WRITE but are applied via the UI, not here.
    return {
        "requires_confirmation": True,
        "message": "Metadata changes are applied from the Videos page (Edit).",
        "proposed": params,
    }


def _create_playlist(db: Session, user: User, channel: Channel, params: dict) -> dict:
    return {
        "requires_confirmation": True,
        "message": "Create playlists from the Playlists page.",
        "proposed": {"title": params.get("title"), "description": params.get("description")},
    }


def _schedule_upload(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.models.content_plan_item import ContentPlanItem

    title = params.get("title", "Scheduled upload")
    item = ContentPlanItem(
        channel_id=channel.id,
        title=title,
        idea=params.get("description") or params.get("idea"),
        status="SCHEDULED",
        publish_date=params.get("publish_date"),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"draft_id": item.id, "status": "SCHEDULED", "message": "Scheduled in the content plan."}


def _upload_video(db: Session, user: User, channel: Channel, params: dict) -> dict:
    return {
        "note": "Upload dilakukan dari halaman Videos (tombol Upload) - AI tidak mengunggah file sendiri.",
        "title": params.get("title", ""),
        "description": params.get("description", ""),
    }


def _generate_title(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.ai.service import generate_titles

    titles = generate_titles(db, channel, topic=params.get("topic"), video_id=params.get("video_id"))
    return {"titles": titles}


def _generate_description(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.ai.service import generate_description

    return {"description": generate_description(db, channel, title=params.get("title"))}


def _generate_seo(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.ai.service import generate_seo

    return generate_seo(db, channel, title=params.get("title"))


def _analyze_video(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.agents.decision_engine import compute_video_score
    from app.models.video import Video

    yid = params.get("video_id") or params.get("youtube_video_id")
    if not yid:
        raise AppError(400, "VALIDATION_ERROR", "video_id is required.")
    video = db.query(Video).filter_by(channel_id=channel.id, youtube_video_id=yid).first()
    if video is None:
        raise AppError(404, "NOT_FOUND", "Video not found.")
    return compute_video_score(video)


def _analyze_channel(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.agents.decision_engine import compute_video_score
    from app.models.video import Video

    videos = db.query(Video).filter(Video.channel_id == channel.id).all()
    scores = [compute_video_score(v) for v in videos]
    valid = [s for s in scores if s.get("score") is not None]
    avg = round(sum(s["score"] for s in valid) / len(valid), 1) if valid else None
    return {
        "channel": channel.title,
        "average_ai_score": avg,
        "video_count": len(videos),
        "note": "Heuristic performance score, not an official YouTube metric.",
    }


def _traffic_sources(db: Session, user: User, channel: Channel, params: dict) -> dict:
    """Live views-by-traffic-source (recommendations, search, external...) for the channel."""
    from app.models.youtube_account import YouTubeAccount
    from app.services.youtube_service import TRAFFIC_SOURCE_LABELS, YouTubeService
    from app.youtube.client import get_analytics_client

    account = db.get(YouTubeAccount, channel.youtube_account_id)
    if account is None:
        return {"note": "No connected YouTube account for this channel.", "items": []}
    days = min(max(int(params.get("days", 28)), 1), 365)
    try:
        client = get_analytics_client(db, account)
        items = YouTubeService().get_traffic_sources(client, account.channel_id, days)
    except Exception as exc:  # noqa: BLE001
        return {"note": f"Sumber traffic tidak bisa diambil dari YouTube: {exc}", "items": []}
    total = sum(i["views"] for i in items)
    return {
        "items": items,
        "total_views": total,
        "note": f"Penayangan {days} hari terakhir menurut sumber traffic. "
        "Label penting: Rekomendasi video = video yang direkomendasikan YouTube; "
        "Pencarian YouTube = hasil pencarian.",
    }


def _create_content_plan(db: Session, user: User, channel: Channel, params: dict) -> dict:
    from app.models.content_plan_item import ContentPlanItem

    ideas = params.get("items") or []
    created = []
    for idea in ideas[:20]:
        title = idea.get("title") if isinstance(idea, dict) else str(idea)
        item = ContentPlanItem(
            channel_id=channel.id,
            title=title[:500],
            description=(idea.get("description") if isinstance(idea, dict) else None),
            target_keyword=(idea.get("target_keyword") if isinstance(idea, dict) else None),
            status="IDEA",
        )
        db.add(item)
        created.append(title[:500])
    db.commit()
    return {"created": len(created), "items": created}


TOOLS: dict[str, Tool] = {
    "get_channel_info": Tool("get_channel_info", "Get basic channel statistics.", PermissionLevel.READ, _channel_stats),
    "get_channel_videos": Tool("get_channel_videos", "List recent videos of the channel.", PermissionLevel.READ, _channel_videos),
    "get_video_analytics": Tool("get_video_analytics", "Get analytics for one video.", PermissionLevel.READ, _video_analytics),
    "get_channel_analytics": Tool("get_channel_analytics", "Get channel analytics for the last 28 days.", PermissionLevel.READ, _channel_analytics),
    "get_traffic_sources": Tool("get_traffic_sources", "Get views by traffic source (video recommendations, search, external...) for the channel.", PermissionLevel.READ, _traffic_sources),
    "search_channel_videos": Tool("search_channel_videos", "Search videos by title.", PermissionLevel.READ, _search_videos),
    "get_comments": Tool("get_comments", "Get live comments for the channel (optionally filter by video_id).", PermissionLevel.READ, _get_comments),
    "reply_comment": Tool("reply_comment", "Reply to a comment (requires approval, posts to YouTube).", PermissionLevel.HIGH_RISK, _reply_comment),
    "create_video_draft": Tool("create_video_draft", "Create a video idea/draft in the content plan.", PermissionLevel.WRITE, _create_video_draft),
    "update_video_metadata": Tool("update_video_metadata", "Propose metadata changes for a video.", PermissionLevel.WRITE, _update_video_metadata),
    "create_playlist": Tool("create_playlist", "Propose creating a playlist.", PermissionLevel.WRITE, _create_playlist),
    "schedule_upload": Tool("schedule_upload", "Schedule an upload in the content plan.", PermissionLevel.WRITE, _schedule_upload),
    "upload_video": Tool("upload_video", "Upload a video (requires approval).", PermissionLevel.HIGH_RISK, _upload_video),
    "generate_title": Tool("generate_title", "Generate video titles.", PermissionLevel.READ, _generate_title),
    "generate_description": Tool("generate_description", "Generate a video description.", PermissionLevel.READ, _generate_description),
    "generate_seo": Tool("generate_seo", "Generate SEO keywords and tags.", PermissionLevel.READ, _generate_seo),
    "analyze_video": Tool("analyze_video", "Analyze a video's performance.", PermissionLevel.READ, _analyze_video),
    "analyze_channel": Tool("analyze_channel", "Analyze the channel's performance.", PermissionLevel.READ, _analyze_channel),
    "create_content_plan": Tool("create_content_plan", "Create content plan items from a list.", PermissionLevel.WRITE, _create_content_plan),
}


def execute_tool(db: Session, user: User, channel: Channel, name: str, params: dict | None = None) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        raise AppError(400, "UNKNOWN_TOOL", f"Unknown tool: {name}")
    if tool.permission == PermissionLevel.HIGH_RISK:
        # HIGH_RISK tools NEVER execute directly: the handler routes the action
        # through the approval system and returns requires_approval.
        return tool.handler(db, user, channel, params or {})
    gate = PermissionGate()
    if not gate.check_tool(tool.permission):
        raise AppError(403, "FORBIDDEN", f"Tool {name} requires {tool.permission.name} permission.")
    return tool.handler(db, user, channel, params or {})
