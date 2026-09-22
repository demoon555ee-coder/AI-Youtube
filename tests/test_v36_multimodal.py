import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.multimodal_graph.service import MultimodalProductionGraphService
from app.vision.mock import MockVisionProvider


def _project(data):
    return SimpleNamespace(id=uuid4(), channel_id=uuid4(), data=data)


def _make_mp4(path: Path):
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "1.4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]


def test_preflight_builds_multimodal_graph_and_catches_audio_overrun():
    project = _project({
        "script": {"title": "Test", "narration": "This is a long narration with many words that will exceed the very short scene duration."},
        "scene_director": {"scenes": [
            {"scene": 1, "duration": 0.5, "narration": "This is a long narration with many words that will exceed the very short scene duration.", "visual_prompt": "show a server room"},
            {"scene": 2, "duration": 4.0, "narration": "Second scene", "visual_prompt": "show a city at night"},
        ]},
        "content_intelligence": {"format": "explainer"},
    })
    result = asyncio.run(MultimodalProductionGraphService(vision_provider=MockVisionProvider()).build_preflight(project=project))
    assert result["stage"] == "pre_render"
    assert result["nodes"]
    assert result["edges"]
    assert any(c["type"] == "audio_overrun_risk" for c in result["conflicts"])
    assert any(n["type"] == "timeline" for n in result["nodes"])
    assert result["signals"]["vision_mode"] == "predicted"


def test_post_render_graph_combines_media_and_multimodal_vision(tmp_path):
    video = tmp_path / "video.mp4"
    _make_mp4(video)
    project = _project({
        "script": {"title": "Test", "narration": "A concise narration."},
        "scene_director": {"scenes": [
            {"scene": 1, "duration": 0.7, "narration": "First scene", "visual_goal": "Topic", "visual_prompt": "server room"},
            {"scene": 2, "duration": 0.7, "narration": "Second scene", "visual_goal": "Result", "visual_prompt": "city skyline"},
        ]},
        "production": {"assets": []},
        "editor": {"output_path": str(video), "timeline": [{"scene": 1}, {"scene": 2}]},
        "creative_intelligence": {"scene_reports": [], "score": 92, "issues": []},
    })
    result = asyncio.run(MultimodalProductionGraphService(vision_provider=MockVisionProvider(), output_dir=str(tmp_path)).analyze_rendered(project=project))
    assert result["stage"] == "post_render"
    assert result["signals"]["media"]["has_video"] is True
    assert result["signals"]["media"]["has_audio"] is True
    assert result["signals"]["vision_mode"] == "mock"
    assert result["signals"]["vision_analysis"]["images_analyzed"] >= 4
    assert any(n["id"] == "media:final" for n in result["nodes"])


def test_graph_marks_missing_visual_intent_as_high_risk():
    project = _project({"scene_director": {"scenes": [{"scene": 1, "duration": 2, "narration": "hello", "visual_prompt": ""}]}})
    result = asyncio.run(MultimodalProductionGraphService(vision_provider=MockVisionProvider()).build_preflight(project=project))
    assert result["status"] == "FAIL"
    assert any(c["type"] == "missing_visual_intent" and c["severity"] == "high" for c in result["conflicts"])


def test_openai_vision_provider_supports_multi_image_responses_contract():
    source = Path("app/vision/openai.py").read_text()
    assert "analyze_multimodal" in source
    assert "input_image" in source
    assert "input_text" in source
    assert "/responses" in source


class CaptureVisionProvider(MockVisionProvider):
    def __init__(self):
        self.captured = ""

    async def analyze_multimodal(self, *, image_paths, prompt):
        self.captured = prompt
        return await super().analyze_multimodal(image_paths=image_paths, prompt=prompt)


def test_post_render_multimodal_prompt_includes_audio_subtitles_and_timeline(tmp_path):
    video = tmp_path / "video.mp4"
    _make_mp4(video)
    srt = tmp_path / "subtitles.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,800\nFirst scene\n", encoding="utf-8")
    project = _project({
        "script": {"title": "Test", "narration": "A concise narration."},
        "scene_director": {"scenes": [
            {"scene": 1, "duration": 0.7, "narration": "First scene", "visual_goal": "Topic", "visual_prompt": "server room"},
            {"scene": 2, "duration": 0.7, "narration": "Second scene", "visual_goal": "Result", "visual_prompt": "city skyline"},
        ]},
        "production": {"assets": []},
        "editor": {"output_path": str(video), "subtitle_path": str(srt), "timeline": [{"scene": 1, "start": 0, "end": 0.7}, {"scene": 2, "start": 0.7, "end": 1.4}]},
        "creative_intelligence": {"scene_reports": [], "score": 92, "issues": []},
    })
    provider = CaptureVisionProvider()
    result = asyncio.run(MultimodalProductionGraphService(vision_provider=provider, output_dir=str(tmp_path)).analyze_rendered(project=project))
    assert result["signals"]["subtitle_text_present"] is True
    assert "subtitles.srt" not in provider.captured  # prompt gets subtitle content, not a local path
    assert "First scene" in provider.captured
    assert "timeline" in provider.captured
    assert "mean_volume_db" in provider.captured


def test_post_render_rejects_media_outside_output_dir(tmp_path):
    outside = tmp_path.parent / "outside.mp4"
    _make_mp4(outside)
    project = _project({"editor": {"output_path": str(outside)}})
    service = MultimodalProductionGraphService(vision_provider=MockVisionProvider(), output_dir=str(tmp_path / "allowed"))
    try:
        asyncio.run(service.analyze_rendered(project=project))
    except ValueError as exc:
        assert "outside the configured output directory" in str(exc)
    else:
        raise AssertionError("Expected output path isolation error")
