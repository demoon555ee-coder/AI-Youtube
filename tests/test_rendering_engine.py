from __future__ import annotations

import pytest

from app.config import settings
from app.rendering.service import RenderService


@pytest.mark.asyncio
async def test_render_service_uses_remotion(monkeypatch, tmp_path):
    calls: list[str] = []

    async def fake_remotion(self, **kwargs):
        calls.append("remotion")
        return {"render_status": "completed", "render_engine": "remotion"}

    async def fake_ffmpeg(self, **kwargs):
        calls.append("ffmpeg")
        return {"render_status": "completed", "render_engine": "ffmpeg"}

    monkeypatch.setattr("app.rendering.remotion.RemotionRenderer.render_video", fake_remotion)
    monkeypatch.setattr(RenderService, "_render_video_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(settings, "render_engine", "remotion")

    service = RenderService(str(tmp_path))
    result = await service.render_video(project_id="project", storyboard={"scenes": [{"duration": 1}]})

    assert result["render_engine"] == "remotion"
    assert calls == ["remotion"]


@pytest.mark.asyncio
async def test_render_service_auto_falls_back_to_ffmpeg(monkeypatch, tmp_path):
    calls: list[str] = []

    async def fake_remotion(self, **kwargs):
        calls.append("remotion")
        raise RuntimeError("chromium unavailable")

    async def fake_ffmpeg(self, **kwargs):
        calls.append("ffmpeg")
        return {"render_status": "completed", "render_engine": "ffmpeg"}

    monkeypatch.setattr("app.rendering.remotion.RemotionRenderer.render_video", fake_remotion)
    monkeypatch.setattr(RenderService, "_render_video_ffmpeg", fake_ffmpeg)
    monkeypatch.setattr(settings, "render_engine", "auto")

    service = RenderService(str(tmp_path))
    result = await service.render_video(project_id="project", storyboard={"scenes": [{"duration": 1}]})

    assert result["render_engine"] == "ffmpeg"
    assert "chromium unavailable" in result["render_fallback_reason"]
    assert calls == ["remotion", "ffmpeg"]


@pytest.mark.asyncio
async def test_render_service_remotion_mode_does_not_hide_failures(monkeypatch, tmp_path):
    async def fake_remotion(self, **kwargs):
        raise RuntimeError("renderer contract failure")

    monkeypatch.setattr("app.rendering.remotion.RemotionRenderer.render_video", fake_remotion)
    monkeypatch.setattr(settings, "render_engine", "remotion")

    service = RenderService(str(tmp_path))
    with pytest.raises(RuntimeError, match="renderer contract failure"):
        await service.render_video(project_id="project", storyboard={"scenes": [{"duration": 1}]})


def test_default_render_engine_preserves_existing_ffmpeg_path():
    assert settings.model_fields["render_engine"].default == "ffmpeg"
