from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VideoProject, VideoQualityReport


class VideoQualityService:
    """Deterministic pre/post render quality gate.

    The service deliberately reports measurable facts and separates WARN from FAIL.
    Provider-specific visual semantic review can be added later without weakening the gate.
    """

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def evaluate(self, *, project: VideoProject, output: dict[str, Any], stage: str = "pre_publish", organization_id=None, portfolio_id=None) -> dict[str, Any]:
        output_path = Path(str(output.get("output_path") or ""))
        subtitle_path = Path(str(output.get("subtitle_path") or "")) if output.get("subtitle_path") else None
        storyboard = ((project.data or {}).get("scene_director") or (project.data or {}).get("storyboard") or {}).get("scenes", [])
        production_assets = (((project.data or {}).get("production") or {}).get("assets") or [])

        checks: dict[str, Any] = {}
        issues: list[str] = []
        recommendations: list[str] = []
        score = 100.0

        file_exists = output_path.exists() and output_path.is_file()
        checks["file_exists"] = file_exists
        if not file_exists:
            issues.append("Rendered output is missing")
            score -= 60
            media = {"duration_seconds": 0.0, "width": 0, "height": 0, "has_audio": False, "has_video": False}
        else:
            media = await probe_media(output_path)

        checks["file_size_bytes"] = output_path.stat().st_size if file_exists else 0
        if checks["file_size_bytes"] < 10_000:
            issues.append("Rendered output is unexpectedly small")
            score -= 10

        checks["duration_positive"] = media["duration_seconds"] > 0
        if not checks["duration_positive"]:
            issues.append("Video duration is invalid")
            score -= 25

        checks["has_video_stream"] = media["has_video"]
        checks["has_audio_stream"] = media["has_audio"]
        if not media["has_video"]:
            issues.append("Video stream is missing")
            score -= 30
        if not media["has_audio"]:
            issues.append("Audio stream is missing")
            recommendations.append("Regenerate narration/audio before publication.")
            score -= 15

        pixels = media["width"] * media["height"]
        checks["resolution"] = {"width": media["width"], "height": media["height"], "pixels": pixels}
        if pixels < 921_600:
            issues.append("Resolution is below HD")
            score -= 15
        if media["width"] and media["height"]:
            aspect = media["width"] / media["height"]
            checks["aspect_ratio"] = round(aspect, 4)
            if aspect < 0.45 or aspect > 2.25:
                issues.append("Unusual aspect ratio")
                score -= 8

        checks["subtitle_file"] = bool(subtitle_path and subtitle_path.exists() and subtitle_path.stat().st_size > 10)
        if storyboard and not checks["subtitle_file"]:
            issues.append("Expected subtitle file is missing or empty")
            score -= 8

        scene_count = len(storyboard)
        asset_count = len(production_assets)
        checks["scene_count"] = scene_count
        checks["asset_count"] = asset_count
        if scene_count and asset_count < scene_count:
            issues.append("Production asset coverage is incomplete")
            recommendations.append("Regenerate missing scene assets before publishing.")
            score -= 15

        # Duration sanity against storyboard expectations. A severe mismatch is more useful
        # than a generic pass from file existence alone.
        expected = 0.0
        for scene in storyboard:
            try:
                expected += float(scene.get("duration", 0) or 0)
            except (TypeError, ValueError):
                continue
        if expected and media["duration_seconds"]:
            delta = abs(media["duration_seconds"] - expected) / expected
            checks["storyboard_duration_delta_pct"] = round(delta * 100, 2)
            if delta > 0.25:
                issues.append("Rendered duration differs materially from storyboard")
                score -= 10

        score = max(0.0, min(100.0, round(score, 2)))
        status = "FAIL" if any(i in issues for i in ("Rendered output is missing", "Video stream is missing", "Video duration is invalid")) or score < 60 else ("WARN" if issues else "PASS")
        result = {
            "status": status,
            "score": score,
            "duration_seconds": round(media["duration_seconds"], 3),
            "width": media["width"],
            "height": media["height"],
            "checks": checks,
            "issues": issues,
            "recommendations": recommendations,
        }
        if self.db is not None:
            row = VideoQualityReport(
                organization_id=organization_id,
                portfolio_id=portfolio_id,
                channel_id=project.channel_id,
                project_id=project.id,
                stage=stage,
                status=status,
                score=score,
                duration_seconds=result["duration_seconds"],
                width=media["width"],
                height=media["height"],
                checks=checks,
                issues=issues,
                recommendations=recommendations,
            )
            self.db.add(row)
            await self.db.flush()
            result["report_id"] = str(row.id)
        return result


async def probe_media(path: Path) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-show_entries", "format=duration",
        "-of", "json", str(path), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[-2000:])
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe returned invalid JSON") from exc
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {
        "duration_seconds": float(((payload.get("format") or {}).get("duration") or 0) or 0),
        "width": int((video or {}).get("width") or 0),
        "height": int((video or {}).get("height") or 0),
        "has_video": video is not None,
        "has_audio": has_audio,
    }
