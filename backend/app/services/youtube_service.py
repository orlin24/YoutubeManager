"""YouTube service layer - all YouTube API interaction lives here.

Routers and agents must never talk to the YouTube API directly.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models.analytics_snapshot import AnalyticsSnapshot
from app.models.channel import Channel
from app.models.video import Video
from app.models.youtube_account import YouTubeAccount
from app.services.audit_service import log_audit
import socket
import time

from httplib2.error import RedirectMissingLocation

from app.utils.errors import AppError
from app.utils.logging import get_logger

# YouTube Analytics insightTrafficSourceType -> label bahasa Indonesia
TRAFFIC_SOURCE_LABELS: dict[str, str] = {
    "RELATED_VIDEO": "Rekomendasi video",
    "YT_SEARCH": "Pencarian YouTube",
    "EXT_URL": "Situs luar",
    "PLAYLIST": "Playlist",
    "SHORTS": "Shorts feed",
    "NOTIFICATION": "Notifikasi",
    "SUBSCRIBER": "Pelanggan",
    "BROWSE_FEATURES": "Penjelajahan fitur",
    "YT_CHANNEL": "Halaman channel",
    "ADVERTISEMENT": "Iklan",
    "END_SCREEN": "Layar akhir",
    "YT_OTHER_PAGE": "Halaman YouTube lain",
    "NO_LINK_OTHER": "Lainnya",
    "NO_LINK_EMBEDDED": "Embedded tanpa link",
    "HASHTAG": "Hashtag",
    "LIVE_REDIRECT": "Redirect live",
    "CAMPAIGN_CARD": "Kartu kampanye",
    "ANNOTATION": "Anotasi",
    "PROMOTED": "Dipromosikan",
}
from app.youtube.client import get_analytics_client, get_authenticated_client, safe_call

logger = get_logger("youtube.service")

DEFAULT_CATEGORY = "22"  # People & Blogs


def _parse_iso_duration(duration: str) -> int | None:
    """Convert ISO 8601 duration (PT1H2M3S) to seconds."""
    if not duration:
        return None
    seconds = 0
    import re

    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not m:
        return None
    hours, minutes, secs = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + secs


class YouTubeService:
    """Stateless wrapper around the YouTube Data API."""

    def get_channel(self, client, channel_id: str | None = None) -> dict:
        params: dict[str, Any] = {"part": "snippet,statistics,contentDetails"}
        if channel_id:
            params["id"] = channel_id
        else:
            params["mine"] = "true"
        resp = safe_call(client.channels().list, **params)
        items = resp.get("items", [])
        if not items:
            raise AppError(404, "YOUTUBE_NOT_FOUND", "Channel not found.")
        return _channel_dict(items[0])

    def get_channels(self, client, ids: list[str] | None = None) -> list[dict]:
        params: dict[str, Any] = {"part": "snippet,statistics"}
        if ids:
            params["id"] = ",".join(ids)
        else:
            params["mine"] = "true"
        resp = safe_call(client.channels().list, **params)
        return [_channel_dict(i) for i in resp.get("items", [])]

    def get_videos(self, client, channel_id: str, max_results: int = 50) -> list[dict]:
        """List a channel's videos via the uploads playlist (playlistItems).

        Uses playlistItems instead of search: search costs 100 quota units per
        call (easy to exhaust the daily limit), playlistItems costs 1 unit.
        """
        playlist_id = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else f"UU{channel_id}"
        ids: list[str] = []
        next_token: str | None = None
        while len(ids) < max_results:
            params: dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(50, max_results - len(ids)),
            }
            if next_token:
                params["pageToken"] = next_token
            resp = safe_call(client.playlistItems().list, **params)
            for item in resp.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    ids.append(vid)
            next_token = resp.get("nextPageToken")
            if not next_token:
                break
        if not ids:
            return []
        detail = safe_call(
            client.videos().list,
            part="snippet,contentDetails,statistics,status",
            id=",".join(ids[:50]),
        )
        return [_video_dict(v) for v in detail.get("items", [])]

    def get_video(self, client, video_id: str) -> dict:
        resp = safe_call(client.videos().list, part="snippet,contentDetails,statistics,status", id=video_id)
        items = resp.get("items", [])
        if not items:
            raise AppError(404, "YOUTUBE_NOT_FOUND", "Video not found.")
        return _video_dict(items[0])

    def update_video(
        self,
        client,
        video_id: str,
        title=None,
        description=None,
        privacy_status=None,
        tags: list[str] | None = None,
    ) -> dict:
        current = self.get_video(client, video_id)
        # videos().update replaces the snippet/status - re-send existing values unless overridden.
        body = {
            "id": video_id,
            "snippet": {
                "title": title or current.get("title", ""),
                "description": description if description is not None else current.get("description", ""),
                "categoryId": DEFAULT_CATEGORY,
                "tags": tags if tags is not None else current.get("tags", []),
            },
            "status": {
                "privacyStatus": privacy_status or current.get("privacy_status", "private"),
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": current.get("contains_synthetic_media", True),
            },
        }
        resp = safe_call(client.videos().update, part="snippet,status", body=body)
        return _video_dict(resp)

    def upload_video(
        self,
        client,
        *,
        file_path: str,
        title: str,
        description: str,
        privacy_status: str = "private",
        publish_at: datetime | None = None,
        tags: list[str] | None = None,
        mimetype: str = "video/mp4",
        contains_synthetic_media: bool = True,
        progress_cb: Callable[[float], None] | None = None,
        session_cb: Callable[[str], None] | None = None,
        resume_uri: str | None = None,
    ) -> dict:
        from googleapiclient.http import MediaFileUpload

        snippet: dict = {"title": title, "description": description, "categoryId": DEFAULT_CATEGORY}
        if tags:
            snippet["tags"] = tags[:50]
        status_body: dict = {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": contains_synthetic_media,
        }
        if publish_at is not None:
            # Scheduled publishing: privacy must be 'private' + publishAt set.
            # YouTube makes the video public automatically at publishAt.
            status_body["privacyStatus"] = "private"
            status_body["publishAt"] = publish_at.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        body = {"snippet": snippet, "status": status_body}
        # Resumable file upload: no size limit, streams from disk (YouTube allows
        # up to 256GB / 12h per video). next_chunk() reports upload progress.
        media = MediaFileUpload(file_path, mimetype=mimetype, resumable=True, chunksize=1024 * 1024)  # 1MB chunks: ISP proxies block large PUTs
        request = client.videos().insert(part="snippet,status", body=body, media_body=media)
        if resume_uri:
            request.resumable_uri = resume_uri  # continue an interrupted session
        response = None
        redirect_retries = 3
        while response is None:
            # num_retries: transient network/5xx errors are retried automatically
            # and the resumable session continues from the last uploaded position.
            try:
                status, response = request.next_chunk(num_retries=3)
            except RedirectMissingLocation:
                # ISPs/proxies sometimes answer a large chunk PUT with a bare
                # 3xx (no Location). The chunk is idempotent - retry it.
                redirect_retries -= 1
                if redirect_retries <= 0:
                    # Last chunk may have succeeded despite the proxy 3xx -
                    # probe the resumable session: if the video exists, treat
                    # the upload as COMPLETED instead of failed.
                    probe = _probe_resumable_session(request)
                    if probe is not None:
                        response = probe
                        break
                    raise
                time.sleep(2)
                continue
            except (socket.timeout, TimeoutError, ConnectionError) as exc:
                redirect_retries -= 1
                if redirect_retries <= 0:
                    raise
                time.sleep(3)
                continue
            if status is not None:
                if session_cb is not None and request.resumable_uri:
                    session_cb(request.resumable_uri)
                if progress_cb is not None:
                    total = float(status.total_size or 0)
                    if total:
                        progress_cb(min(status.resumable_progress / total, 1.0))
        resp = response
        video = _video_dict(resp)
        # fetch contentDetails/stats for the fresh upload
        try:
            detail = safe_call(client.videos().list, part="contentDetails,statistics", id=resp["id"])
            if detail.get("items"):
                video.update(_video_dict(detail["items"][0]))
        except Exception:  # noqa: BLE001
            pass
        return video

    def delete_video(self, client, video_id: str) -> None:
        safe_call(client.videos().delete, id=video_id)

    def get_playlists(self, client, channel_id: str | None = None) -> list[dict]:
        params: dict[str, Any] = {"part": "snippet,contentDetails"}
        if channel_id:
            params["channelId"] = channel_id
        else:
            params["mine"] = "true"
        resp = safe_call(client.playlists().list, **params)
        return [
            {
                "id": p["id"],
                "title": p.get("snippet", {}).get("title", ""),
                "description": p.get("snippet", {}).get("description", ""),
                "item_count": int(p.get("contentDetails", {}).get("itemCount", 0) or 0),
                "thumbnail_url": p.get("snippet", {}).get("thumbnails", {}).get("medium", {}).get("url", ""),
            }
            for p in resp.get("items", [])
        ]

    def create_playlist(self, client, title: str, description: str = "") -> dict:
        resp = safe_call(
            client.playlists().insert,
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": "private"},
            },
        )
        return {"id": resp["id"], "title": title, "description": description, "item_count": 0}

    def update_playlist(self, client, playlist_id: str, title=None, description=None) -> dict:
        resp = safe_call(
            client.playlists().list, part="snippet", id=playlist_id
        )
        items = resp.get("items", [])
        if not items:
            raise AppError(404, "YOUTUBE_NOT_FOUND", "Playlist not found.")
        snippet = items[0].get("snippet", {})
        body = {
            "id": playlist_id,
            "snippet": {
                "title": title or snippet.get("title", ""),
                "description": description if description is not None else snippet.get("description", ""),
            },
        }
        out = safe_call(client.playlists().update, part="snippet", body=body)
        return {"id": out["id"], "title": out.get("snippet", {}).get("title", ""),
                "description": out.get("snippet", {}).get("description", ""), "item_count": 0}

    def get_comments(self, client, video_id: str | None = None, max_results: int = 50,
                     video_ids: list[str] | None = None) -> list[dict]:
        """Fetch comment threads.

        - video_id: only that video.
        - video_ids: a bounded list of the channel's recent videos - fetch a few
          threads per video. This works for Brand/managed channels where the
          allThreadsRelatedToChannelId parameter is restricted.
        Falls back to allThreadsRelatedToChannelId when no video is known.
        """
        ids = ([video_id] if video_id else (video_ids or []))[:6]
        out: list[dict] = []
        if ids:
            per_video = max(3, min(max_results, max_results // len(ids) + 1))
            for vid in ids:
                if len(out) >= max_results:
                    break
                try:
                    resp = safe_call(
                        client.commentThreads().list, part="snippet", textFormat="plainText",
                        videoId=vid, maxResults=per_video,
                    )
                except AppError:
                    continue  # private / deleted / comments disabled - skip
                out.extend(self._extract_threads(resp.get("items", [])))
            return out[:max_results]
        # no known video: try the channel-scope parameter (owned channels only)
        resp = safe_call(
            client.commentThreads().list, part="snippet", textFormat="plainText",
            allThreadsRelatedToChannelId=True, maxResults=max_results,
        )
        return self._extract_threads(resp.get("items", []))

    @staticmethod
    def _extract_threads(items: list[dict]) -> list[dict]:
        out = []
        for t in items:
            c = t.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            out.append(
                {
                    "id": t.get("id", ""),
                    "video_id": t.get("snippet", {}).get("videoId", ""),
                    "video_title": "",
                    "author": c.get("authorDisplayName", ""),
                    "text": c.get("textOriginal", ""),
                    "like_count": int(c.get("likeCount", 0) or 0),
                    "published_at": c.get("publishedAt", ""),
                    "sentiment": None,
                }
            )
        return out

    def reply_comment(self, client, comment_id: str, text: str) -> dict:
        resp = safe_call(
            client.comments().insert,
            part="snippet",
            body={"snippet": {"parentId": comment_id, "textOriginal": text}},
        )
        return {"id": resp.get("id", ""), "text": text}

    def set_thumbnail(self, client, video_id: str, file_bytes: bytes, mimetype: str = "image/jpeg") -> dict:
        """Upload a custom thumbnail (JPEG/PNG/WEBP, max 2MB, 16:9 recommended)."""
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype, resumable=False)
        # safe_call invokes .execute() on the returned request object.
        resp = safe_call(lambda: client.thumbnails().set(videoId=video_id, media_body=media))
        items = resp.get("items", [])
        if not items:
            raise AppError(404, "YOUTUBE_NOT_FOUND", "Thumbnail upload did not return a result.")
        # thumbnails.set returns the urls DIRECTLY on the item (items[0].high.url),
        # not nested under snippet.thumbnails - reading the wrong path silently
        # lost the url and the app never stored the thumbnail.
        meta = items[0]
        url = (
            meta.get("high", {}).get("url")
            or meta.get("maxres", {}).get("url")
            or meta.get("medium", {}).get("url")
            or meta.get("default", {}).get("url", "")
        )
        return {"youtube_video_id": video_id, "thumbnail_url": url}

    def set_thumbnail_when_ready(
        self, client, video_id: str, file_bytes: bytes, mimetype: str = "image/jpeg",
        timeout_s: int = 420,
    ) -> dict:
        """Set a thumbnail, waiting for YouTube to finish processing the video.

        Right after an upload finishes, YouTube is still transcoding the video
        and thumbnails.set fails (403/409 "processing"). Poll processingDetails
        until it succeeds, then retry the thumbnail a few times.
        """
        import time

        deadline = time.monotonic() + timeout_s
        # Phase 1: wait until the video is no longer processing.
        while time.monotonic() < deadline:
            try:
                resp = safe_call(client.videos().list, part="processingDetails", id=video_id)
                item = (resp.get("items") or [{}])[0]
                status = item.get("processingDetails", {}).get("processingStatus")
                if status in (None, "succeeded", "failed"):
                    break
            except AppError:
                pass
            time.sleep(15)
        # Phase 2: upload the thumbnail, retrying transient rejections.
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.set_thumbnail(client, video_id, file_bytes, mimetype)
            except AppError as exc:
                last_error = exc
                time.sleep(10)
        raise last_error or AppError(
            408, "THUMBNAIL_TIMEOUT",
            "Waktu habis menunggu thumbnail bisa di-set - coba lagi dari Edit video.",
        )

    def get_traffic_sources(self, analytics_client, channel_id: str, days: int = 28) -> list[dict]:
        """Views broken down by traffic source (e.g. video recommendations, search),
        so the AI can reason about WHERE the channel's views come from."""
        from datetime import date, timedelta

        today = date.today()
        start = today - timedelta(days=days - 1)
        resp = safe_call(
            analytics_client.reports().query,
            ids=f"channel=={channel_id}",
            startDate=start.isoformat(),
            endDate=today.isoformat(),
            metrics="views",
            dimensions="insightTrafficSourceType",
            sort="-views",
        )
        rows = resp.get("rows", [])
        cols = [c["name"] for c in resp.get("columnHeaders", [])]
        total = sum(int(r[cols.index("views")] or 0) for r in rows) if rows and "views" in cols else 0
        out: list[dict] = []
        for row in rows:
            vals = dict(zip(cols, row))
            key = vals.get("insightTrafficSourceType", "")
            views = int(vals.get("views", 0) or 0)
            out.append(
                {
                    "source": key,
                    "label": TRAFFIC_SOURCE_LABELS.get(key, key),
                    "views": views,
                    "percent": round(views / total * 100, 1) if total else 0.0,
                }
            )
        return out

    def get_views_last_7d(self, analytics_client, channel_id: str) -> list[dict]:
        """Daily channel views for the last 7 days, via the Analytics API.

        Note: the Analytics API has no 'hour' dimension, so hourly views are not
        available through the official API. Daily bars are real data; view counts
        are estimates when first reported and may be adjusted as data is refined.
        """
        from datetime import date, timedelta

        today = date.today()
        start = today - timedelta(days=6)
        resp = safe_call(
            analytics_client.reports().query,
            ids=f"channel=={channel_id}",
            startDate=start.isoformat(),
            endDate=today.isoformat(),
            metrics="views,estimatedMinutesWatched",
            dimensions="day",
        )
        rows = resp.get("rows", [])
        cols = [c["name"] for c in resp.get("columnHeaders", [])]
        data: dict[str, dict] = {}
        for row in rows:
            vals = dict(zip(cols, row))
            day = vals.get("day", "")
            data[day] = {
                "date": day,
                "views": int(vals.get("views", 0) or 0),
                "watch_time_seconds": float(vals.get("estimatedMinutesWatched", 0) or 0) * 60,
            }
        # Fill all 7 days so the chart is complete (missing = 0 views).
        return [
            data.get(
                (start + timedelta(days=i)).isoformat(),
                {"date": (start + timedelta(days=i)).isoformat(), "views": 0, "watch_time_seconds": 0.0},
            )
            for i in range(7)
        ]


# ---------------------------------------------------------------------------
# DB-facing flow helpers used by routers / agents / tasks
# ---------------------------------------------------------------------------


def _channel_dict(item: dict) -> dict:
    sn = item.get("snippet", {})
    st = item.get("statistics", {})
    return {
        "channel_id": item.get("id", ""),
        "title": sn.get("title", ""),
        "description": sn.get("description", ""),
        "thumbnail_url": sn.get("thumbnails", {}).get("high", {}).get("url", ""),
        "subscriber_count": int(st.get("subscriberCount", 0) or 0),
        "view_count": int(st.get("viewCount", 0) or 0),
        "video_count": int(st.get("videoCount", 0) or 0),
    }




def _probe_resumable_session(request) -> dict | None:
    """GET the resumable session: 200 + video body = upload actually completed
    (the redirect was just the proxy's answer to the final chunk)."""
    try:
        import json as _json

        resp, content = request.http.request(request.resumable_uri, method="GET")
        if resp.status == 200 and content:
            data = _json.loads(content.decode("utf-8"))
            if data.get("id"):
                return data
    except Exception:  # noqa: BLE001
        pass
    return None


def _video_dict(item: dict) -> dict:
    sn = item.get("snippet", {})
    st = item.get("statistics", {})
    cd = item.get("contentDetails", {})
    status = item.get("status", {})
    return {
        "youtube_video_id": item.get("id", ""),
        "title": sn.get("title", ""),
        "description": sn.get("description", ""),
        "tags": sn.get("tags", []),
        "thumbnail_url": sn.get("thumbnails", {}).get("high", {}).get("url", ""),
        "published_at": sn.get("publishedAt"),
        "duration_seconds": _parse_iso_duration(cd.get("duration", "")),
        "view_count": int(st.get("viewCount", 0) or 0),
        "like_count": int(st.get("likeCount", 0) or 0),
        "comment_count": int(st.get("commentCount", 0) or 0),
        "privacy_status": status.get("privacyStatus", "private"),
        "contains_synthetic_media": bool(status.get("containsSyntheticMedia", True)),
        "ctr": None,
        "average_view_duration_seconds": None,
        "ai_score": None,
    }


def _upsert_video(db: Session, channel: Channel, data: dict) -> Video:
    video = (
        db.query(Video)
        .filter_by(channel_id=channel.id, youtube_video_id=data["youtube_video_id"])
        .first()
    )
    published = data.get("published_at")
    if published and isinstance(published, str):
        try:
            published = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError:
            published = None
    fields = {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "thumbnail_url": data.get("thumbnail_url", ""),
        "published_at": published,
        "duration_seconds": data.get("duration_seconds"),
        "view_count": data.get("view_count", 0),
        "like_count": data.get("like_count", 0),
        "comment_count": data.get("comment_count", 0),
        "privacy_status": data.get("privacy_status", "private"),
    }
    if video is None:
        video = Video(channel_id=channel.id, youtube_video_id=data["youtube_video_id"], **fields)
        db.add(video)
    else:
        for k, v in fields.items():
            setattr(video, k, v)
    db.commit()
    db.refresh(video)
    return video


def sync_channel_data(db: Session, account: YouTubeAccount, *, full: bool = True) -> dict:
    """Sync channel stats + recent videos + today's channel snapshot. Idempotent."""
    client = get_authenticated_client(db, account)
    channel = db.query(Channel).filter_by(youtube_account_id=account.id).first()
    if channel is None:
        raise AppError(404, "NOT_FOUND", "Channel row missing; reconnect the account.")

    info = YouTubeService().get_channel(client, channel.channel_id)
    channel.title = info["title"]
    channel.description = info["description"]
    channel.thumbnail_url = info["thumbnail_url"]
    channel.subscriber_count = info["subscriber_count"]
    channel.view_count = info["view_count"]
    channel.video_count = info["video_count"]
    db.commit()

    if full:
        videos = YouTubeService().get_videos(client, channel.channel_id, max_results=50)
        for v in videos:
            _upsert_video(db, channel, v)

    metrics: dict | None = None
    try:
        aclient = get_analytics_client(db, account)
        metrics = _fetch_channel_daily_metrics(aclient, channel.channel_id, date.today())
    except AppError as exc:
        logger.warning("Channel analytics unavailable, storing zeros: %s", exc.code)
    _upsert_channel_snapshot(db, channel, metrics)
    refresh_channel_scores(db, channel.id)  # auto AI scores for every video
    log_audit(db, channel_id=channel.id, action="channel_synced", target=channel.title, result="ok")
    return {
        "channel_id": channel.channel_id,
        "title": channel.title,
        "subscriber_count": channel.subscriber_count,
        "view_count": channel.view_count,
        "video_count": channel.video_count,
    }


def _upsert_channel_snapshot(db: Session, channel: Channel, metrics: dict | None = None) -> None:
    """Store a daily channel-level analytics snapshot (DAILY DELTAS).

    metrics comes from the YouTube Analytics API for [today-1, today]; when it is
    unavailable (degraded mode), deltas are stored as 0 - we never fabricate data.
    """
    today = date.today()
    snapshot = (
        db.query(AnalyticsSnapshot)
        .filter_by(channel_id=channel.id, video_id=None, date=today)
        .first()
    )
    if snapshot is None:
        snapshot = AnalyticsSnapshot(channel_id=channel.id, video_id=None, date=today)
        db.add(snapshot)
    m = metrics or {}
    snapshot.views = int(m.get("views", 0) or 0)
    snapshot.watch_time_seconds = float(m.get("estimatedMinutesWatched", 0) or 0) * 60
    snapshot.average_view_duration_seconds = float(m.get("averageViewDuration", 0) or 0)
    snapshot.likes = int(m.get("likes", 0) or 0)
    snapshot.comments = int(m.get("comments", 0) or 0)
    snapshot.shares = int(m.get("shares", 0) or 0)
    snapshot.subscribers_gained = int(m.get("subscribersGained", 0) or 0)
    snapshot.subscribers_lost = int(m.get("subscribersLost", 0) or 0)
    revenue = m.get("estimatedRevenue")
    snapshot.estimated_revenue = float(revenue) if revenue is not None else None
    db.commit()


def _fetch_channel_daily_metrics(client, channel_id: str, today: date) -> dict:
    """Channel-level analytics for the last day. Returns {} on failure.

    estimatedRevenue needs the restricted yt-analytics-monetary scope, which we no
    longer request (it blocks unverified apps from new sign-ins). Accounts granted
    before keep it; for others we retry without the revenue metric.
    """
    metrics = (
        "views,estimatedMinutesWatched,averageViewDuration,likes,comments,shares,"
        "subscribersGained,subscribersLost,estimatedRevenue"
    )
    try:
        resp = safe_call(
            client.reports().query,
            ids=f"channel=={channel_id}",
            startDate=(today - timedelta(days=1)).isoformat(),
            endDate=today.isoformat(),
            metrics=metrics,
        )
    except AppError as exc:
        if exc.code == "YOUTUBE_PERMISSION" and "estimatedRevenue" in metrics:
            resp = safe_call(
                client.reports().query,
                ids=f"channel=={channel_id}",
                startDate=(today - timedelta(days=1)).isoformat(),
                endDate=today.isoformat(),
                metrics=metrics.replace(",estimatedRevenue", ""),
            )
        else:
            raise
    rows = resp.get("rows", [])
    if not rows:
        return {}
    cols = [c["name"] for c in resp.get("columnHeaders", [])]
    return dict(zip(cols, rows[0]))


def sync_video_analytics(db: Session, account: YouTubeAccount, video: Video | None = None) -> None:
    """Refresh per-video metrics (avg view duration) from the Analytics API.

    Uses ONE batched query per 20 videos over the last 28 days (dimensions=video),
    so the WATCH TIME column (average view duration) is filled for every video with
    any views in the window. Cumulative counters come from the Data API.

    Note: the public YouTube Analytics API does NOT expose impressions, so CTR
    cannot be filled from this data (it only exists in YouTube Studio).
    """
    channel = db.query(Channel).filter_by(youtube_account_id=account.id).first()
    if channel is None:
        return
    today = date.today()
    start = (today - timedelta(days=27)).isoformat()
    client = get_analytics_client(db, account)
    videos = [video] if video is not None else db.query(Video).filter_by(channel_id=channel.id).all()

    by_ytid = {v.youtube_video_id: v for v in videos}

    # Batched aggregate queries (max 20 video filters per call).
    ids = list(by_ytid.keys())
    for i in range(0, len(ids), 20):
        batch = ids[i : i + 20]
        try:
            resp = safe_call(
                client.reports().query,
                ids=f"channel=={channel.channel_id}",
                startDate=start,
                endDate=today.isoformat(),
                metrics="views,estimatedMinutesWatched,averageViewDuration,likes,comments",
                dimensions="video",
                filters=f"video=={','.join(batch)}",
            )
        except AppError as exc:
            if exc.code == "YOUTUBE_AUTH_EXPIRED":
                raise
            logger.warning("Analytics batch failed: %s", exc.code)
            continue
        cols = [c["name"] for c in resp.get("columnHeaders", [])]
        for row in resp.get("rows", []):
            vals = dict(zip(cols, row))
            v = by_ytid.get(vals.get("video", ""))
            if v is None:
                continue
            avg_dur = vals.get("averageViewDuration")
            if avg_dur is not None:
                v.average_view_duration_seconds = float(avg_dur)
            v.ctr = None  # impressions/CTR are not available via the public API
        db.commit()

    # Refresh cumulative counters from the Data API (best-effort).
    try:
        data_client = get_authenticated_client(db, account)
        for v in videos[:20]:
            try:
                detail = YouTubeService().get_video(data_client, v.youtube_video_id)
                v.view_count = detail["view_count"]
                v.like_count = detail["like_count"]
                v.comment_count = detail["comment_count"]
                db.commit()
            except AppError as exc:
                logger.warning("Video detail refresh failed for %s: %s", v.youtube_video_id, exc.code)
    except AppError as exc:
        logger.warning("Cumulative counters refresh skipped: %s", exc.code)


def update_video_metadata(db: Session, account: YouTubeAccount, video: Video, **fields) -> Video:
    client = get_authenticated_client(db, account)
    privacy = fields.get("privacy_status")
    YouTubeService().update_video(
        client,
        video.youtube_video_id,
        title=fields.get("title"),
        description=fields.get("description"),
        privacy_status=privacy,
        tags=fields.get("tags"),
    )
    if "title" in fields:
        video.title = fields["title"]
    if "description" in fields:
        video.description = fields["description"]
    if privacy:
        video.privacy_status = privacy
    db.commit()
    db.refresh(video)
    log_audit(
        db, channel_id=video.channel_id, action="video_metadata_updated",
        target=video.title, result="ok", metadata={"fields": list(fields.keys())},
    )
    return video


def _resolve_account_for_video(db: Session, video: Video) -> YouTubeAccount:
    ch = video.channel
    if ch is None or ch.youtube_account is None:
        raise AppError(404, "NOT_FOUND", "YouTube account not found for this video.")
    return ch.youtube_account


def publish_video(db: Session, account: YouTubeAccount, video: Video) -> Video:
    client = get_authenticated_client(db, account)
    YouTubeService().update_video(client, video.youtube_video_id, privacy_status="public")
    video.privacy_status = "public"
    db.commit()
    db.refresh(video)
    log_audit(db, channel_id=video.channel_id, action="video_published", target=video.title, result="ok")
    return video


def set_video_visibility(db: Session, account: YouTubeAccount, video: Video, status: str) -> Video:
    client = get_authenticated_client(db, account)
    YouTubeService().update_video(client, video.youtube_video_id, privacy_status=status)
    video.privacy_status = status
    db.commit()
    db.refresh(video)
    log_audit(db, channel_id=video.channel_id, action="video_visibility_changed",
              target=video.title, result=status)
    return video


def delete_video_flow(db: Session, account: YouTubeAccount, video: Video) -> dict:
    client = get_authenticated_client(db, account)
    YouTubeService().delete_video(client, video.youtube_video_id)
    title = video.title
    db.delete(video)
    db.commit()
    log_audit(db, channel_id=video.channel_id, action="video_deleted", target=title, result="ok")
    return {"deleted": True, "title": title}


def reply_to_comment(db: Session, account: YouTubeAccount, comment_id: str, text: str) -> dict:
    client = get_authenticated_client(db, account)
    result = YouTubeService().reply_comment(client, comment_id, text)
    log_audit(db, channel_id=account.channel.id if account.channel else None,
              action="comment_replied", target=comment_id, result="ok")
    return result


def update_video_thumbnail(
    db: Session, account: YouTubeAccount, video: Video, file_bytes: bytes, mimetype: str
) -> Video:
    client = get_authenticated_client(db, account)
    # Tunggu video selesai diproses YouTube dulu (penting untuk upload baru),
    # lalu set thumbnail dengan retry. Endpoint Edit tetap instan (video lama).
    result = YouTubeService().set_thumbnail_when_ready(
        client, video.youtube_video_id, file_bytes, mimetype
    )
    if result.get("thumbnail_url"):
        video.thumbnail_url = result["thumbnail_url"]
        db.commit()
        db.refresh(video)
    log_audit(db, channel_id=video.channel_id, action="video_thumbnail_updated",
              target=video.title, result="ok")
    return video


def refresh_channel_scores(db: Session, channel_id: str) -> dict:
    """Compute and store the AI Performance Score for EVERY video of a channel.

    Pure computation from stored data - no YouTube API calls - so it is safe to
    run automatically on every sync and on demand.
    """
    from app.agents.decision_engine import compute_video_score

    videos = db.query(Video).filter_by(channel_id=channel_id).all()
    with_score = 0
    without = 0
    for v in videos:
        result = compute_video_score(v)
        score = result.get("score")
        v.ai_score = score
        if score is not None:
            with_score += 1
        else:
            without += 1
    db.commit()
    return {"scored": len(videos), "with_score": with_score, "without": without}
