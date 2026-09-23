from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.media.pexels import PexelsPhotoProvider, PexelsVideoProvider


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


def _response(status: int, *, json_data=None, content=b"", url="https://provider.test", method="GET"):
    if json_data is not None:
        return httpx.Response(status, json=json_data, request=httpx.Request(method, url))
    return httpx.Response(status, content=content, request=httpx.Request(method, url))


def test_pexels_photo_provider_searches_and_downloads(monkeypatch, tmp_path):
    fake = _FakeClient([
        _response(200, json_data={
            "photos": [{
                "id": 101,
                "width": 1920,
                "height": 1080,
                "url": "https://www.pexels.com/photo/test-101/",
                "photographer": "Test Photographer",
                "photographer_url": "https://www.pexels.com/@test",
                "src": {
                    "landscape": "https://images.pexels.com/photos/101/test.jpg",
                },
            }]
        }),
        _response(200, content=b"JPEGDATA", url="https://images.pexels.com/photos/101/test.jpg"),
    ])
    monkeypatch.setattr("app.media.pexels.httpx.AsyncClient", lambda **_: fake)

    provider = PexelsPhotoProvider(api_key="pexels-test")
    result = asyncio.run(provider.generate_scene_asset(
        prompt="cinematic city skyline",
        output_path=str(tmp_path / "scene.png"),
        width=1920,
        height=1080,
    ))

    assert result["provider"] == "pexels_photo"
    assert Path(result["path"]).suffix == ".jpg"
    assert Path(result["path"]).read_bytes() == b"JPEGDATA"
    assert result["attribution"]["creator"] == "Test Photographer"
    assert fake.calls[0][2]["headers"]["Authorization"] == "pexels-test"
    assert fake.calls[0][2]["params"]["orientation"] == "landscape"
    assert fake.calls[0][2]["params"]["per_page"] == 12


def test_pexels_video_provider_selects_hd_mp4_and_preserves_attribution(monkeypatch, tmp_path):
    fake = _FakeClient([
        _response(200, json_data={
            "videos": [{
                "id": 202,
                "width": 1920,
                "height": 1080,
                "duration": 12,
                "url": "https://www.pexels.com/video/test-202/",
                "user": {
                    "name": "Test Videographer",
                    "url": "https://www.pexels.com/@videographer",
                },
                "video_files": [
                    {
                        "id": 1,
                        "quality": "sd",
                        "file_type": "video/mp4",
                        "width": 640,
                        "height": 360,
                        "link": "https://player.vimeo.com/external/test.sd.mp4",
                    },
                    {
                        "id": 2,
                        "quality": "hd",
                        "file_type": "video/mp4",
                        "width": 1920,
                        "height": 1080,
                        "link": "https://player.vimeo.com/external/test.hd.mp4",
                    },
                ],
            }]
        }),
        _response(200, content=b"MP4DATA", url="https://player.vimeo.com/external/test.hd.mp4"),
    ])
    monkeypatch.setattr("app.media.pexels.httpx.AsyncClient", lambda **_: fake)

    provider = PexelsVideoProvider(api_key="pexels-test")
    result = asyncio.run(provider.generate_scene_asset(
        prompt="office b-roll",
        output_path=str(tmp_path / "scene.png"),
        width=1920,
        height=1080,
        duration_seconds=5,
        metadata={"asset_type": "broll"},
    ))

    assert result["provider"] == "pexels_video"
    assert Path(result["path"]).suffix == ".mp4"
    assert Path(result["path"]).read_bytes() == b"MP4DATA"
    assert result["attribution"]["text"] == "Video by Test Videographer on Pexels"
    assert fake.calls[0][1].endswith("/videos/search")
    assert fake.calls[0][2]["params"]["orientation"] == "landscape"
    assert fake.calls[1][1] == "https://player.vimeo.com/external/test.hd.mp4"


def test_pexels_provider_rejects_untrusted_media_hosts():
    try:
        PexelsPhotoProvider._validate_download_url(
            "https://evil.example/media.jpg",
            {"images.pexels.com"},
        )
    except ValueError:
        return
    raise AssertionError("Untrusted Pexels media host was accepted")


def test_pexels_provider_requires_api_key():
    try:
        PexelsVideoProvider(api_key="")
    except RuntimeError as exc:
        assert "PEXELS_API_KEY" in str(exc)
        return
    raise AssertionError("Pexels provider accepted an empty API key")
