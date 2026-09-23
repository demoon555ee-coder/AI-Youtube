from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import httpx

from app.media.runway_video import RunwayVideoProvider
from app.tts.elevenlabs import ElevenLabsTTSProvider


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


def _resp(status, json_data=None, content=b"", method="POST", url="https://provider.test"):
    if json_data is not None:
        return httpx.Response(status, json=json_data, request=httpx.Request(method, url))
    return httpx.Response(status, content=content, request=httpx.Request(method, url))


def test_runway_provider_submits_image_to_video_and_downloads(monkeypatch, tmp_path):
    fake = _FakeClient([
        _resp(200, {"id": "task-1"}),
        _resp(200, {"id": "task-1", "status": "SUCCEEDED", "output": ["https://cdn.cloudfront.net/video.mp4?token=x"]}, method="GET", url="https://api.dev.runwayml.com/v1/tasks/task-1"),
        _resp(200, content=b"MP4DATA", method="GET", url="https://cdn.cloudfront.net/video.mp4?token=x"),
    ])
    monkeypatch.setattr("app.media.runway_video.httpx.AsyncClient", lambda **_: fake)
    async def no_sleep(_):
        return None
    monkeypatch.setattr("app.media.runway_video.asyncio.sleep", no_sleep)

    source = tmp_path / "scene.png"
    source.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))

    provider = RunwayVideoProvider(api_key="k", poll_seconds=5, timeout_seconds=30)
    result = asyncio.run(provider.generate_scene_asset(
        prompt="A cinematic test motion",
        output_path=str(tmp_path / "clip.png"),
        width=1920,
        height=1080,
        duration_seconds=5,
        metadata={"image_path": str(source)},
    ))

    assert result["provider"] == "runway"
    assert Path(result["path"]).suffix == ".mp4"
    assert Path(result["path"]).read_bytes() == b"MP4DATA"
    assert fake.calls[0][1].endswith("/image_to_video")
    payload = fake.calls[0][2]["json"]
    assert payload["model"] == "gen4.5"
    assert payload["ratio"] == "1280:720"
    assert payload["duration"] == 5
    assert payload["promptImage"].startswith("data:image/")


def test_elevenlabs_provider_normalizes_pcm_to_wav(monkeypatch, tmp_path):
    pcm = b"\x00\x00" * 1600
    fake = _FakeClient([
        _resp(200, content=pcm, method="POST", url="https://api.elevenlabs.io/v1/text-to-speech/voice")
    ])
    monkeypatch.setattr("app.tts.elevenlabs.httpx.AsyncClient", lambda **_: fake)

    provider = ElevenLabsTTSProvider(
        api_key="k",
        voice_id="voice",
        model="eleven_flash_v2_5",
    )
    out = tmp_path / "voice.wav"
    result = asyncio.run(provider.synthesize("Hello from the test", out))

    assert out.exists()
    assert out.read_bytes()[:4] == b"RIFF"
    assert result["provider"] == "elevenlabs"
    assert result["response_format"] == "wav"
    assert result["voice"] == "voice"
    assert fake.calls[0][2]["headers"]["xi-api-key"] == "k"
    assert "output_format=pcm_16000" in fake.calls[0][1]


def test_runway_output_url_guard_rejects_untrusted_host():
    try:
        RunwayVideoProvider._validate_output_url("https://evil.example/video.mp4")
    except ValueError:
        return
    raise AssertionError("Untrusted Runway output host was accepted")

    
def test_asset_factory_seeds_runway_with_an_image(monkeypatch, tmp_path):
    from app.media.service import AssetFactory

    class FakeImage:
        name = "mock_png"
        async def generate_scene_asset(self, *, prompt, output_path, **kwargs):
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"PNG")
            return {"provider": self.name, "path": str(path)}

    class FakeRunway:
        name = "runway"
        def __init__(self):
            self.image_path = None
        async def generate_scene_asset(self, *, prompt, output_path, metadata, **kwargs):
            self.image_path = metadata.get("image_path")
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"MP4")
            return {"provider": self.name, "path": str(path), "status": "completed"}

    fake_image = FakeImage()
    fake_runway = FakeRunway()
    monkeypatch.setattr("app.media.service.get_image_provider", lambda *_args, **_kwargs: fake_image)
    monkeypatch.setattr("app.media.service.get_video_provider", lambda *_args, **_kwargs: fake_runway)

    result = asyncio.run(AssetFactory(
        str(tmp_path), image_provider="mock_png", video_provider="runway"
    ).build_for_storyboard(
        project_id="runway-seed",
        storyboard={"scenes": [
            {"scene": 1, "duration": 2, "asset_type": "video", "visual_prompt": "city sunrise"},
        ]},
    ))

    assert Path(fake_runway.image_path).exists()
    assert Path(fake_runway.image_path).name == "seed_scene_001.png"
    assert result["assets"][0]["source"] == "runway"
    assert result["assets"][0]["path"].endswith("scene_001.mp4")

    
def test_runway_provider_exposes_safe_api_error(monkeypatch, tmp_path):
    fake = _FakeClient([
        _resp(400, {"error": "You do not have enough credits to run this task."}),
    ])
    monkeypatch.setattr("app.media.runway_video.httpx.AsyncClient", lambda **_: fake)
    provider = RunwayVideoProvider(api_key="k", poll_seconds=5, timeout_seconds=30)

    try:
        asyncio.run(provider.generate_scene_asset(
            prompt="test",
            output_path=str(tmp_path / "clip.mp4"),
            metadata={},
        ))
    except RuntimeError as exc:
        assert "enough credits" in str(exc)
        return
    raise AssertionError("Runway API error was not surfaced")
