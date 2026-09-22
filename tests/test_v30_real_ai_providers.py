from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.media.http_video import HTTPVideoProvider
from app.media.openai_image import OpenAIImageProvider
from app.tts.openai import OpenAITTSProvider


class _FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        item=self.responses.pop(0)
        return item
    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


def _resp(status, json_data=None, content=b"", method="POST", url="https://provider.test"):
    if json_data is not None:
        return httpx.Response(status, json=json_data, request=httpx.Request(method, url))
    return httpx.Response(status, content=content, request=httpx.Request(method, url))


def test_openai_image_provider_downloads_base64(monkeypatch, tmp_path):
    import base64
    png=base64.b64encode(b"PNGDATA").decode()
    fake=_FakeClient([_resp(200,{"data":[{"b64_json":png}],"usage":{"total_tokens":12}})])
    monkeypatch.setattr("app.media.openai_image.httpx.AsyncClient",lambda **_: fake)
    provider=OpenAIImageProvider(api_key="k",model="gpt-image-2")
    result=asyncio.run(provider.generate_scene_asset(prompt="test",output_path=str(tmp_path/"scene.jpg")))
    assert Path(result["path"]).suffix==".png"
    assert Path(result["path"]).read_bytes()==b"PNGDATA"
    assert fake.calls[0][2]["json"]["model"]=="gpt-image-2"


def test_openai_tts_provider_writes_wav(monkeypatch,tmp_path):
    fake=_FakeClient([_resp(200,content=b"RIFFWAV",method="POST",url="https://api.openai.com/v1/audio/speech")])
    monkeypatch.setattr("app.tts.openai.httpx.AsyncClient",lambda **_: fake)
    provider=OpenAITTSProvider(api_key="k",model="gpt-4o-mini-tts",voice="alloy")
    out=tmp_path/"voice.wav"
    result=asyncio.run(provider.synthesize("hello",out))
    assert out.read_bytes()==b"RIFFWAV"
    assert result["provider"]=="openai_tts"
    assert fake.calls[0][2]["json"]["response_format"]=="wav"


def test_http_video_provider_polls_and_downloads(monkeypatch,tmp_path):
    fake=_FakeClient([
        _resp(200,{"id":"job1","status_url":"https://provider.test/jobs/job1","status":"queued"}),
        _resp(200,{"status":"completed","download_url":"https://provider.test/output/job1.mp4"},method="GET",url="https://provider.test/jobs/job1"),
        _resp(200,content=b"MP4DATA",method="GET",url="https://provider.test/output/job1.mp4"),
    ])
    monkeypatch.setattr("app.media.http_video.httpx.AsyncClient",lambda **_: fake)
    async def no_sleep(_): return None
    monkeypatch.setattr("app.media.http_video.asyncio.sleep",no_sleep)
    provider=HTTPVideoProvider(endpoint="https://provider.test/generate",api_key="k",poll_seconds=.1,timeout_seconds=5)
    result=asyncio.run(provider.generate_scene_asset(prompt="test",output_path=str(tmp_path/"scene.png")))
    assert result["external_job_id"]=="job1"
    assert Path(result["path"]).suffix==".mp4"
    assert Path(result["path"]).read_bytes()==b"MP4DATA"
    assert [x[0] for x in fake.calls]==["POST","GET","GET"]


def test_asset_factory_routes_motion_scenes_to_video_provider(tmp_path):
    from app.media.service import AssetFactory

    result = asyncio.run(AssetFactory(
        str(tmp_path), image_provider="mock_png", video_provider="mock_video"
    ).build_for_storyboard(
        project_id="motion-project",
        storyboard={"scenes": [
            {"scene": 1, "duration": 0.7, "asset_type": "image", "visual_prompt": "still"},
            {"scene": 2, "duration": 0.7, "asset_type": "video", "visual_prompt": "motion"},
        ]},
    ))
    by_scene = {item["scene"]: item for item in result["assets"]}
    assert by_scene[1]["path"].endswith(".png")
    assert by_scene[1]["source"] == "mock_png"
    assert by_scene[2]["path"].endswith(".mp4")
    assert by_scene[2]["source"] == "mock_video"
    assert result["providers"] == {"image": "mock_png", "video": "mock_video"}


def test_render_service_consumes_real_motion_asset(tmp_path):
    from app.media.service import AssetFactory
    from app.rendering.service import RenderService, probe_duration

    project_id = "render-project"
    assets = asyncio.run(AssetFactory(
        str(tmp_path), image_provider="mock_png", video_provider="mock_video"
    ).build_for_storyboard(
        project_id=project_id,
        storyboard={"scenes": [
            {"scene": 1, "duration": 0.8, "asset_type": "video", "narration": "Motion scene", "visual_prompt": "motion"},
        ]},
    ))
    result = asyncio.run(RenderService(str(tmp_path), tts_provider="espeak").render_video(
        project_id=project_id,
        storyboard={"scenes": [
            {"scene": 1, "duration": 0.8, "narration": "Motion scene", "on_screen_text": "Motion"},
        ]},
        assets=assets["assets"],
        language="en",
    ))
    output = Path(result["output_path"])
    assert output.exists()
    assert output.stat().st_size > 0
    assert asyncio.run(probe_duration(output)) > 0.5
    assert Path(result["subtitle_path"]).exists()



def test_http_video_provider_does_not_forward_bearer_to_cdn_by_default(monkeypatch, tmp_path):
    fake = _FakeClient([
        _resp(200, {"id": "job2", "status": "completed", "download_url": "https://provider.test/output/job2.mp4"}),
        _resp(200, content=b"MP4DATA", method="GET", url="https://provider.test/output/job2.mp4"),
    ])
    monkeypatch.setattr("app.media.http_video.httpx.AsyncClient", lambda **_: fake)
    provider = HTTPVideoProvider(endpoint="https://provider.test/generate", api_key="secret", timeout_seconds=5)
    asyncio.run(provider.generate_scene_asset(prompt="test", output_path=str(tmp_path / "scene.png")))
    assert "Authorization" not in fake.calls[-1][2].get("headers", {})


def test_split_text_for_tts_never_exceeds_chunk_limit():
    from app.rendering.service import split_text_for_tts
    chunks = split_text_for_tts("word " * 2000, max_chars=100)
    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)
