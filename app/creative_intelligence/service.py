from __future__ import annotations
import asyncio
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import CreativeAnalysis, VideoProject
from app.quality.service import probe_media
from app.vision import get_vision_provider


class CreativeIntelligenceService:
    """Scene-level creative QA with deterministic media signals and optional vision AI."""

    def __init__(self, db: AsyncSession | None = None, vision_provider=None):
        self.db = db
        self.vision = vision_provider or get_vision_provider()

    async def analyze(self, *, project: VideoProject, stage: str = "post_render", organization_id=None) -> dict[str, Any]:
        editor = (project.data or {}).get("editor") or {}
        output_path = Path(str(editor.get("output_path") or ""))
        if not output_path.is_file():
            result = {"status": "FAIL", "score": 0.0, "issues": ["Rendered output is missing"], "recommendations": [], "scene_reports": [], "visual_analysis": {}, "audio_analysis": {}, "reedit_plan": {}}
            return await self._persist(project, result, stage, organization_id)

        storyboard = ((project.data or {}).get("scene_director") or (project.data or {}).get("storyboard") or {}).get("scenes", [])
        media = await probe_media(output_path)
        duration = float(media["duration_seconds"] or 0)
        sample_times = self._sample_times(duration, len(storyboard))
        with tempfile.TemporaryDirectory(prefix="creative-") as tmp:
            frame_paths = []
            for idx, timestamp in enumerate(sample_times, start=1):
                path = Path(tmp) / f"frame_{idx:03d}.jpg"
                await self._extract_frame(output_path, timestamp, path)
                if path.is_file():
                    frame_paths.append((timestamp, path))

            visual = await self._visual_metrics(frame_paths)
            audio = await self._audio_metrics(output_path)
            scene_reports = await self._scene_reports(frame_paths, storyboard, duration)

        issues: list[str] = []
        recommendations: list[str] = []
        score = 100.0
        if visual["duplicate_transition_count"] > 0:
            score -= min(25.0, visual["duplicate_transition_count"] * 8.0)
            issues.append("Consecutive sampled frames are visually too similar")
            recommendations.append("Increase visual variation or cut faster in repetitive sections.")
        if visual["low_information_frames"]:
            score -= min(20.0, len(visual["low_information_frames"]) * 5.0)
            issues.append("Some sampled frames have unusually low visual information")
            recommendations.append("Replace low-information frames with clearer visual evidence or tighter motion.")
        if audio.get("mean_volume_db") is not None and audio["mean_volume_db"] < -35:
            score -= 15
            issues.append("Average audio level is unusually low")
            recommendations.append("Raise narration level or normalize the final mix.")
        mismatches = [r for r in scene_reports if r.get("narration_visual_alignment", 1.0) < 0.55]
        if mismatches:
            score -= min(25.0, len(mismatches) * 8.0)
            issues.append("Some scenes show possible narration-to-visual mismatch")
            recommendations.append("Re-edit the flagged scenes so the visual explicitly supports the spoken claim.")

        reedit = {
            "mode": "targeted_scene_reedit",
            "source_project_id": str(project.id),
            "scenes": [
                {
                    "scene": r["scene"],
                    "reason": r.get("issues") or ["weak_scene_signal"],
                    "actions": r.get("recommendations") or ["replace_or_tighten_visual"],
                    "time_range": [round(r["start_seconds"], 2), round(r["end_seconds"], 2)],
                }
                for r in scene_reports if r.get("issues")
            ],
        }
        status = "FAIL" if any("missing" in i.lower() for i in issues) else ("WARN" if issues else "PASS")
        result = {
            "status": status,
            "score": round(max(0.0, min(100.0, score)), 2),
            "sampled_frames": len(frame_paths),
            "scene_reports": scene_reports,
            "visual_analysis": visual,
            "audio_analysis": audio,
            "issues": issues,
            "recommendations": recommendations,
            "reedit_plan": reedit,
        }
        return await self._persist(project, result, stage, organization_id)

    async def _persist(self, project, result, stage, organization_id):
        if self.db is not None:
            row = CreativeAnalysis(
                organization_id=organization_id, channel_id=project.channel_id, project_id=project.id,
                stage=stage, status=result["status"], score=result["score"],
                sampled_frames=result.get("sampled_frames", 0), scene_reports=result.get("scene_reports", []),
                audio_analysis=result.get("audio_analysis", {}), visual_analysis=result.get("visual_analysis", {}),
                issues=result.get("issues", []), recommendations=result.get("recommendations", []),
                reedit_plan=result.get("reedit_plan", {}),
            )
            self.db.add(row)
            await self.db.flush()
            result["analysis_id"] = str(row.id)
        return result

    def _sample_times(self, duration: float, scene_count: int) -> list[float]:
        if duration <= 0:
            return []
        count = min(settings.creative_max_frames, max(4, scene_count or 0, int(math.ceil(duration / settings.creative_frame_interval_seconds))))
        count = min(count, max(1, int(duration * 2)))
        if count == 1:
            return [0.0]
        return [round((duration - 0.15) * i / (count - 1), 3) for i in range(count)]

    async def _extract_frame(self, video: Path, timestamp: float, output: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-ss", str(max(0.0, timestamp)), "-i", str(video), "-frames:v", "1", "-q:v", "3", str(output),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace")[-2000:])

    async def _visual_metrics(self, frames):
        from PIL import Image, ImageStat
        signatures = []
        low_info = []
        for timestamp, path in frames:
            with Image.open(path) as img:
                img = img.convert("L").resize((32, 18))
                stat = ImageStat.Stat(img)
                pixels = list(img.get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.getdata())
                mean = stat.mean[0]
                std = stat.stddev[0]
                signature = tuple(int(v // 16) for v in pixels)
                signatures.append((timestamp, signature, mean, std))
                if std < 8:
                    low_info.append(round(timestamp, 2))
        duplicate = 0
        similarities = []
        threshold = float(settings.creative_similarity_threshold)
        for a, b in zip(signatures, signatures[1:]):
            diff = sum(abs(x-y) for x, y in zip(a[1], b[1])) / (len(a[1]) * 15.0) if a[1] else 1.0
            similarity = round(1.0 - min(1.0, diff), 4)
            similarities.append(similarity)
            if diff < threshold:
                duplicate += 1
        return {
            "frame_count": len(signatures),
            "duplicate_transition_count": duplicate,
            "similarity_samples": similarities,
            "low_information_frames": low_info,
        }

    async def _audio_metrics(self, video: Path) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", str(video), "-af", "volumedetect", "-f", "null", "-",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        text = stderr.decode("utf-8", errors="replace")
        mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", text)
        max_match = re.search(r"max_volume:\s*(-?[0-9.]+) dB", text)
        return {
            "mean_volume_db": float(mean_match.group(1)) if mean_match else None,
            "max_volume_db": float(max_match.group(1)) if max_match else None,
        }

    async def _scene_reports(self, frames, storyboard, duration: float):
        reports = []
        scene_count = len(storyboard) or 1
        scene_boundaries = []
        cursor = 0.0
        for idx, scene in enumerate(storyboard or [{"scene": 1, "duration": duration}], start=1):
            d = max(0.1, float(scene.get("duration", 0) or 0))
            scene_boundaries.append((idx, cursor, min(duration, cursor + d), scene))
            cursor += d
        for timestamp, path in frames:
            scene_no, start, end, scene = next((row for row in scene_boundaries if row[1] <= timestamp <= max(row[2], row[1])), scene_boundaries[-1])
            prompt = json.dumps({
                "task": "Evaluate whether this frame visually supports the narration.",
                "narration": scene.get("narration", ""),
                "visual_goal": scene.get("visual_goal", ""),
                "visual_prompt": scene.get("visual_prompt", ""),
                "output_json": {"relevance_score": 0.0, "clarity_score": 0.0, "narration_visual_alignment": 0.0, "issues": [], "recommendations": []},
            }, ensure_ascii=False)
            vision = await self.vision.analyze_frame(image_path=str(path), prompt=prompt)
            reports.append({
                "scene": int(scene_no), "start_seconds": round(start, 3), "end_seconds": round(end, 3),
                "sample_time": round(timestamp, 3), "relevance_score": float(vision.get("relevance_score", 0.0)),
                "clarity_score": float(vision.get("clarity_score", 0.0)),
                "narration_visual_alignment": float(vision.get("narration_visual_alignment", 0.0)),
                "issues": list(vision.get("issues") or []), "recommendations": list(vision.get("recommendations") or []),
                "provider": vision.get("_provider", getattr(self.vision, "name", "unknown")),
            })
        return reports


class TargetedReEditService:
    """Patch only flagged scene ranges while preserving the source project's audio and lineage."""

    def __init__(self, output_dir: str, image_provider=None):
        from app.media.factory import get_image_provider
        self.output_dir = Path(output_dir).resolve()
        self.image_provider = image_provider or get_image_provider()

    async def render_patch(
        self,
        *,
        source_project: VideoProject,
        revision_project_id: str,
        scene_patches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        editor = (source_project.data or {}).get("editor") or {}
        source_video = Path(str(editor.get("output_path") or "")).resolve()
        source_srt = Path(str(editor.get("subtitle_path") or "")).resolve() if editor.get("subtitle_path") else None
        if not source_video.is_file():
            raise FileNotFoundError("Source rendered video does not exist")
        try:
            source_video.relative_to(self.output_dir)
        except ValueError as exc:
            raise ValueError("Source video is outside the configured output directory") from exc

        storyboard = ((source_project.data or {}).get("scene_director") or (source_project.data or {}).get("storyboard") or {}).get("scenes", [])
        if not storyboard:
            raise ValueError("Source project has no scene plan")
        by_scene = {int(row.get("scene")): row for row in scene_patches if row.get("scene") is not None}
        source_bounds: list[tuple[int, float, float, dict[str, Any]]] = []
        cursor = 0.0
        for idx, scene in enumerate(storyboard, start=1):
            duration = max(0.1, float(scene.get("duration", 0) or 0))
            source_bounds.append((idx, cursor, cursor + duration, scene))
            cursor += duration

        output_root = self.output_dir / str(revision_project_id) / "evolution_patch"
        output_root.mkdir(parents=True, exist_ok=True)
        replacement_assets: dict[int, Path] = {}
        duration_overrides: dict[int, float] = {}
        for scene_no, patch in by_scene.items():
            scene_info = next((row for row in source_bounds if row[0] == scene_no), None)
            if not scene_info:
                continue
            _, _, _, scene = scene_info
            action = str(patch.get("action") or "replace_visual")
            if action == "tighten":
                multiplier = float((patch.get("parameters") or {}).get("duration_multiplier", 0.82))
                duration_overrides[scene_no] = max(0.25, min(1.0, multiplier))
                continue
            if action not in {"replace_visual", "tighten"}:
                raise ValueError(f"Unsupported automatic re-edit action: {action}")
            requested = str(patch.get("replacement_path") or "").strip()
            if requested:
                candidate = Path(requested).resolve()
                try:
                    candidate.relative_to(self.output_dir)
                except ValueError as exc:
                    raise ValueError("Replacement asset is outside the output directory") from exc
                if not candidate.is_file():
                    raise FileNotFoundError(f"Replacement asset missing for scene {scene_no}")
                replacement_assets[scene_no] = candidate
                continue
            prompt = str(patch.get("prompt") or scene.get("visual_prompt") or scene.get("visual") or f"Improve scene {scene_no} visual")
            result = await self.image_provider.generate_scene_asset(
                prompt=prompt,
                output_path=str(output_root / f"replacement_{scene_no:03d}.png"),
                duration_seconds=max(0.5, float(scene.get("duration", 5) or 5)),
                metadata={"scene": scene_no, "purpose": "targeted_reedit", "revision_project_id": str(revision_project_id)},
            )
            replacement_assets[scene_no] = Path(str(result["path"])).resolve()

        with tempfile.TemporaryDirectory(dir=output_root) as tmp:
            tmp_dir = Path(tmp)
            segments: list[Path] = []
            for scene_no, start, end, scene in source_bounds:
                duration = max(0.1, end - start)
                if scene_no in duration_overrides:
                    duration = max(0.25, duration * duration_overrides[scene_no])
                segment = tmp_dir / f"segment_{scene_no:03d}.mp4"
                replacement = replacement_assets.get(scene_no)
                if replacement:
                    await _run([
                        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source_video),
                        "-loop", "1", "-i", str(replacement),
                        "-filter_complex", "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v]",
                        "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
                        str(segment),
                    ])
                else:
                    await _run([
                        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source_video),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(segment),
                    ])
                segments.append(segment)

            concat = tmp_dir / "segments.txt"
            concat.write_text("\n".join(f"file '{p}'" for p in segments) + "\n", encoding="utf-8")
            patched = output_root / "patched.mp4"
            await _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(patched)])

            final = output_root / "final.mp4"
            if source_srt and source_srt.is_file():
                subtitle_filter = f"subtitles={_escape_filter_path(str(source_srt))}:force_style='FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=40'"
                await _run(["ffmpeg", "-y", "-i", str(patched), "-vf", subtitle_filter, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", str(final)])
            else:
                patched.replace(final)
            return {
                "output_path": str(final),
                "subtitle_path": str(source_srt) if source_srt and source_srt.is_file() else None,
                "duration_seconds": await probe_duration(final),
                "patched_scenes": sorted(set(replacement_assets) | set(duration_overrides)),
                "replacement_assets": {str(k): str(v) for k, v in replacement_assets.items()},
                "duration_overrides": {str(k): v for k, v in duration_overrides.items()},
                "source_project_id": str(source_project.id),
                "revision_project_id": str(revision_project_id),
            }

async def _run(command: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({process.returncode}): {stderr.decode('utf-8', errors='replace')[-4000:]}")

async def probe_duration(path: Path) -> float:
    process = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode("utf-8", errors="replace")[-2000:])
    return float(stdout.decode().strip())
