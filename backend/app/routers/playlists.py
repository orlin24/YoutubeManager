"""Playlists: live CRUD against the YouTube API (WRITE actions)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.routers.deps import get_user_account, get_user_channel
from app.services.audit_service import log_audit
from app.services.youtube_service import YouTubeService
from app.utils.errors import AppError
from app.utils.logging import get_logger
from app.utils.security import check_csrf

router = APIRouter(prefix="/playlists", tags=["playlists"])
logger = get_logger("playlists")


class PlaylistCreate(BaseModel):
    title: str
    description: str = ""


class PlaylistUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


class PlaylistItemAdd(BaseModel):
    video_id: str


@router.get("")
async def list_playlists(channel_id: str | None = None, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)) -> dict:
    if not channel_id:
        raise AppError(422, "VALIDATION_ERROR", "channel_id query parameter is required.")
    account = get_user_account(db, user, channel_id)
    ch = get_user_channel(db, user, channel_id)
    service = YouTubeService()
    from app.youtube.client import get_authenticated_client

    client = await asyncio.to_thread(get_authenticated_client, db, account)
    playlists = await asyncio.to_thread(service.get_playlists, client, ch.channel_id)
    return {"items": playlists, "total": len(playlists)}


@router.post("")
async def create_playlist(payload: PlaylistCreate, request: Request, channel_id: str | None = None,
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    if not channel_id:
        raise AppError(422, "VALIDATION_ERROR", "channel_id query parameter is required.")
    account = get_user_account(db, user, channel_id)
    ch = get_user_channel(db, user, channel_id)
    service = YouTubeService()
    from app.youtube.client import get_authenticated_client

    client = await asyncio.to_thread(get_authenticated_client, db, account)
    playlist = await asyncio.to_thread(service.create_playlist, client, payload.title, payload.description)
    log_audit(db, user_id=user.id, channel_id=ch.id, action="playlist_created",
              target=playlist["title"], result="ok")
    return playlist


@router.patch("/{playlist_id}")
async def update_playlist(playlist_id: str, payload: PlaylistUpdate, request: Request,
                          channel_id: str | None = None, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    if not channel_id:
        raise AppError(422, "VALIDATION_ERROR", "channel_id query parameter is required.")
    account = get_user_account(db, user, channel_id)
    service = YouTubeService()
    from app.youtube.client import get_authenticated_client

    client = await asyncio.to_thread(get_authenticated_client, db, account)
    fields = payload.model_dump(exclude_none=True)
    return await asyncio.to_thread(
        service.update_playlist, client, playlist_id, **fields
    )


@router.get("/{playlist_id}/items")
async def playlist_items(playlist_id: str, channel_id: str | None = None,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    if not channel_id:
        raise AppError(422, "VALIDATION_ERROR", "channel_id query parameter is required.")
    account = get_user_account(db, user, channel_id)
    from app.youtube.client import get_authenticated_client

    client = await asyncio.to_thread(get_authenticated_client, db, account)

    def _fetch():
        resp = client.playlistItems().list(
            part="snippet,contentDetails", playlistId=playlist_id, maxResults=50
        ).execute()
        items = resp.get("items", [])
        return [
            {
                "playlist_item_id": i.get("id", ""),
                "video_id": i.get("contentDetails", {}).get("videoId", ""),
                "title": i.get("snippet", {}).get("title", ""),
                "thumbnail_url": i.get("snippet", {}).get("thumbnails", {}).get("medium", {}).get("url", ""),
                "published_at": i.get("contentDetails", {}).get("videoPublishedAt"),
            }
            for i in items
        ]

    items = await asyncio.to_thread(_fetch)
    return {"items": items, "total": len(items)}


@router.post("/{playlist_id}/items")
async def add_playlist_item(playlist_id: str, payload: PlaylistItemAdd, request: Request,
                            channel_id: str | None = None, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    if not channel_id:
        raise AppError(422, "VALIDATION_ERROR", "channel_id query parameter is required.")
    account = get_user_account(db, user, channel_id)
    ch = get_user_channel(db, user, channel_id)
    from app.youtube.client import get_authenticated_client

    client = await asyncio.to_thread(get_authenticated_client, db, account)
    from app.models.video import Video

    video = db.get(Video, payload.video_id)
    youtube_id = video.youtube_video_id if video else payload.video_id

    def _insert():
        return client.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id, "resourceId": {
                "kind": "youtube#video", "videoId": youtube_id}}},
        ).execute()

    result = await asyncio.to_thread(_insert)
    log_audit(db, user_id=user.id, channel_id=ch.id, action="playlist_item_added",
              target=playlist_id, result="ok", metadata={"video_id": youtube_id})
    return {"added": True, "playlist_item_id": result.get("id", "")}
