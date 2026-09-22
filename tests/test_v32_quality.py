import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.quality.service import VideoQualityService, probe_media


def test_probe_media_reads_real_mp4(tmp_path):
    output = tmp_path / "sample.mp4"
    proc = __import__("subprocess").run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.6",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output),
    ], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    media = asyncio.run(probe_media(output))
    assert media["has_video"] is True
    assert media["has_audio"] is True
    assert media["width"] == 1280
    assert media["height"] == 720
    assert media["duration_seconds"] > 0


def test_quality_gate_fails_missing_video(tmp_path):
    project = SimpleNamespace(id=__import__("uuid").uuid4(), channel_id=__import__("uuid").uuid4(), data={})
    result = asyncio.run(VideoQualityService().evaluate(project=project, output={"output_path": str(tmp_path / "missing.mp4")}, stage="pre_publish"))
    assert result["status"] == "FAIL"
    assert "Rendered output is missing" in result["issues"]


def test_quality_gate_warns_when_audio_is_missing(tmp_path):
    output = tmp_path / "video.mp4"
    proc = __import__("subprocess").run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
    ], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    project = SimpleNamespace(
        id=__import__("uuid").uuid4(),
        channel_id=__import__("uuid").uuid4(),
        data={"storyboard": {"scenes": [{"duration": 0.6}]}, "production": {"assets": [{"id": "a1", "path": str(output)}]}, "organization_id": None, "portfolio_id": None},
    )
    result = asyncio.run(VideoQualityService().evaluate(project=project, output={"output_path": str(output), "subtitle_path": str(tmp_path / "no.srt")}, stage="pre_publish"))
    assert result["status"] == "WARN"
    assert result["checks"]["has_audio_stream"] is False
