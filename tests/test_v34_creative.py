import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

from app.creative_intelligence.service import CreativeIntelligenceService
from app.vision.mock import MockVisionProvider


def _make_mp4(path: Path, with_audio=True):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30", "-t", "1.2"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)]
    else:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]


def test_creative_intelligence_produces_scene_reports(tmp_path):
    video = tmp_path / "video.mp4"
    _make_mp4(video, True)
    project = SimpleNamespace(
        id=__import__("uuid").uuid4(),
        channel_id=__import__("uuid").uuid4(),
        data={
            "editor": {"output_path": str(video)},
            "scene_director": {"scenes": [
                {"scene": 1, "duration": 0.6, "narration": "First scene", "visual_goal": "Show the topic"},
                {"scene": 2, "duration": 0.6, "narration": "Second scene", "visual_goal": "Show the result"},
            ]},
        },
    )
    service = CreativeIntelligenceService(vision_provider=MockVisionProvider())
    result = asyncio.run(service.analyze(project=project))
    assert result["sampled_frames"] >= 2
    assert result["scene_reports"]
    assert "reedit_plan" in result
    assert result["audio_analysis"]["mean_volume_db"] is not None


def test_creative_intelligence_handles_missing_output():
    project = SimpleNamespace(id=__import__("uuid").uuid4(), channel_id=__import__("uuid").uuid4(), data={})
    result = asyncio.run(CreativeIntelligenceService(vision_provider=MockVisionProvider()).analyze(project=project))
    assert result["status"] == "FAIL"
    assert result["issues"] == ["Rendered output is missing"]


def test_vision_openai_provider_uses_responses_endpoint():
    source = Path("app/vision/openai.py").read_text()
    assert "/responses" in source
    assert "input_image" in source
    assert "input_text" in source


def test_targeted_reedit_creates_new_video_without_overwriting_source(tmp_path):
    from app.creative_intelligence.service import TargetedReEditService

    source = tmp_path / "source.mp4"
    _make_mp4(source, True)
    project = SimpleNamespace(
        id=__import__("uuid").uuid4(),
        channel_id=__import__("uuid").uuid4(),
        data={
            "editor": {"output_path": str(source)},
            "scene_director": {"scenes": [
                {"scene": 1, "duration": 0.6, "visual_prompt": "replacement scene one"},
                {"scene": 2, "duration": 0.6, "visual_prompt": "scene two"},
            ]},
        },
    )
    from app.media.mock import MockVisualAssetProvider
    result = asyncio.run(TargetedReEditService(str(tmp_path), image_provider=MockVisualAssetProvider()).render_patch(
        source_project=project,
        revision_project_id=str(__import__("uuid").uuid4()),
        scene_patches=[{"scene": 1, "prompt": "new visual for scene one"}],
    ))
    out = Path(result["output_path"])
    assert out.is_file()
    assert out != source
    assert source.is_file()
    assert result["patched_scenes"] == [1]
    assert result["duration_seconds"] > 0.9
