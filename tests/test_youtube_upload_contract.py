from __future__ import annotations

import importlib


class _FakeUploadRequest:
    def __init__(self):
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        return None, {"id": "video_test_123"}


class _FakeVideos:
    def __init__(self, request):
        self.request = request
        self.kwargs = None

    def insert(self, **kwargs):
        self.kwargs = kwargs
        return self.request


class _FakeThumbnails:
    def __init__(self):
        self.kwargs = None

    def set(self, **kwargs):
        self.kwargs = kwargs
        return self

    def execute(self):
        return {"ok": True}


class _FakeYouTube:
    def __init__(self):
        self.request = _FakeUploadRequest()
        self._videos = _FakeVideos(self.request)
        self._thumbnails = _FakeThumbnails()

    def videos(self):
        return self._videos

    def thumbnails(self):
        return self._thumbnails


def test_youtube_upload_uses_resumable_video_insert_and_thumbnail(monkeypatch, tmp_path):
    try:
        youtube_client = importlib.import_module("app.services.youtube_client")
    except ModuleNotFoundError as exc:
        if exc.name == "googleapiclient":
            import pytest
            pytest.skip("Google API client is installed in CI/runtime images but not this minimal local environment")
        raise

    fake = _FakeYouTube()
    monkeypatch.setattr(youtube_client, "youtube_data_api", lambda credentials: fake)

    video = tmp_path / "final.mp4"
    thumb = tmp_path / "thumb.png"
    video.write_bytes(b"not-real-mp4")
    thumb.write_bytes(b"not-real-png")

    youtube_client.upload_video(
        credentials=object(),
        video_path=str(video),
        title="Test title",
        description="Test description",
        tags=["ai", "test"],
        category_id="22",
        privacy_status="private",
        thumbnail_path=str(thumb),
        publish_at=None,
    )

    body = fake._videos.kwargs["body"]
    assert fake._videos.kwargs["part"] == "snippet,status"
    assert fake._videos.kwargs["media_body"] is not None
    assert body["snippet"]["title"] == "Test title"
    assert body["status"]["privacyStatus"] == "private"
    assert fake.request.calls == 1
    assert fake._thumbnails.kwargs["videoId"] == "video_test_123"
