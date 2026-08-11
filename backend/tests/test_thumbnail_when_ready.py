"""Tests untuk upload thumbnail yang menunggu video selesai diproses YouTube."""
import pytest
from app.services.youtube_service import YouTubeService, update_video_thumbnail
from app.utils.errors import AppError


class FakeVideosList:
    """videos().list yang mengembalikan processingStatus dari daftar.

    Referensi list yang SAMA dipakai setiap pemanggilan (pop mengurangi).
    """

    def __init__(self, statuses):
        self._statuses = statuses

    def list(self, part=None, id=None):
        return FakeVideosListRequest(self._statuses)


class FakeVideosListRequest:
    _poll_calls = 0

    def __init__(self, statuses):
        self._statuses = statuses

    def execute(self):
        FakeVideosListRequest._poll_calls += 1
        if self._statuses:
            status = self._statuses.pop(0)
        else:
            status = "processing"  # tetap memproses sampai timeout
        if status is None:
            return {"items": []}
        return {"items": [{"processingDetails": {"processingStatus": status}}]}


class FakeThumbnailsSet:
    """thumbnails().set yang bisa gagal beberapa kali lalu berhasil."""

    def __init__(self, failures_before_ok=0):
        self._remaining = failures_before_ok
        self.calls = 0

    def set(self, videoId=None, media_body=None):
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise AppError(409, "YOUTUBE_PROCESSING", "Video is still processing.")
        return {"items": [{"high": {"url": "https://i.ytimg.com/thumb.jpg"}}]}


class FakeClient:
    def __init__(self, statuses, failures_before_ok=0):
        self._statuses = list(statuses)
        self._thumb = FakeThumbnailsSet(failures_before_ok)

    def videos(self):
        return FakeVideosList(self._statuses)

    def thumbnails(self):
        return self._thumb

    @property
    def thumbnails_calls(self):
        return self._thumb.calls

    def wait_calls(self):
        return FakeVideosListRequest._poll_calls


def _mock_sleep(monkeypatch):
    import time as _time

    from app.services import youtube_service

    monkeypatch.setattr(_time, "sleep", lambda _s: None)
    # safe_call asli: memanggil fn (request builder) lalu .execute() bila ada.
    # thumbnails().set dipanggil via lambda -> hasilnya dict (tanpa .execute()).
    def _safe(fn, *a, **k):
        result = fn()
        return result.execute() if hasattr(result, "execute") else result

    monkeypatch.setattr(youtube_service, "safe_call", _safe)


def test_set_thumbnail_waits_for_processing_then_succeeds(monkeypatch):
    """Video masih 'processing' -> polling sampai 'succeeded', lalu set thumbnail."""
    from app.services import youtube_service

    _mock_sleep(monkeypatch)
    statuses = ["processing", "processing", "succeeded"]
    client = FakeClient(statuses)
    svc = YouTubeService()
    res = svc.set_thumbnail_when_ready(client, "vid1", b"png", "image/png", timeout_s=120)
    assert res["thumbnail_url"] == "https://i.ytimg.com/thumb.jpg"
    assert client.thumbnails_calls == 1
    assert client.wait_calls() == 3


def test_set_thumbnail_retries_transient_rejection(monkeypatch):
    """thumbnails.set ditolak (masih processing) -> retry sampai berhasil."""
    from app.services import youtube_service

    _mock_sleep(monkeypatch)
    client = FakeClient([None], failures_before_ok=1)
    svc = YouTubeService()
    res = svc.set_thumbnail_when_ready(client, "vid1", b"png", "image/png", timeout_s=120)
    assert res["thumbnail_url"] == "https://i.ytimg.com/thumb.jpg"
    assert client.thumbnails_calls == 2


def test_set_thumbnail_raises_when_timeout(monkeypatch):
    """Video terus processing sampai timeout -> AppError THUMBNAIL_TIMEOUT."""
    from app.services import youtube_service

    _mock_sleep(monkeypatch)
    client = FakeClient(["processing"], failures_before_ok=1)
    svc = YouTubeService()
    with pytest.raises(AppError) as ei:
        svc.set_thumbnail_when_ready(client, "vid1", b"png", "image/png", timeout_s=1)
    assert ei.value.code == "THUMBNAIL_TIMEOUT"
