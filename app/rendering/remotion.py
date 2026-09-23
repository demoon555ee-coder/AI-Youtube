from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from app.config import settings


class RemotionRenderError(RuntimeError):
    """Raised when the Remotion renderer cannot complete a render."""


class RemotionRenderer:
    FPS = 30
    WIDTH = 1920
    HEIGHT = 1080
    COMPOSITION_ID = "YouTubeAIVideo"

    def __init__(self, output_dir: str, *, tts=None):
        self.output_dir = Path(output_dir)
        self.tts = tts

    async def render_video(
        self,
        *,
        project_id: str,
        storyboard: dict[str, Any],
        assets: list[dict[str, Any]] | None = None,
        language: str = "en",
        voice: str | None = None,
    ) -> dict[str, Any]:
        scenes = storyboard.get("scenes", [])
        if not scenes:
            raise ValueError("Storyboard contains no scenes")
        if self.tts is None:
            raise ValueError("RemotionRenderer requires a TTS provider")

        project_dir = self.output_dir / project_id
        public_dir = project_dir / "remotion_public"
        asset_dir = public_dir / "assets"
        manifest_path = project_dir / "remotion_manifest.json"
        output_path = project_dir / "final.mp4"
        srt_path = project_dir / "subtitles.srt"
        captions_path = project_dir / "captions.json"

        project_dir.mkdir(parents=True, exist_ok=True)
        if public_dir.exists():
            shutil.rmtree(public_dir)
        asset_dir.mkdir(parents=True, exist_ok=True)

        from app.rendering.service import (
            probe_duration,
            synthesize_with_chunking,
            write_srt,
        )

        asset_by_scene = {
            int(asset["scene"]): asset
            for asset in (assets or [])
            if asset.get("scene") is not None
        }

        manifest_scenes: list[dict[str, Any]] = []
        subtitle_rows: list[tuple[float, float, str]] = []
        cursor_seconds = 0.0

        for index, raw_scene in enumerate(scenes, start=1):
            scene_number = int(raw_scene.get("scene", index))
            narration = str(raw_scene.get("narration") or raw_scene.get("visual") or "").strip()
            requested_duration = max(float(raw_scene.get("duration", 1) or 1), 0.5)

            audio_source = asset_dir / f"voice_{scene_number:03d}.wav"
            await synthesize_with_chunking(
                self.tts,
                narration,
                audio_source,
                language=language,
                voice=voice,
            )
            audio_duration = await probe_duration(audio_source)
            duration_seconds = max(requested_duration, audio_duration + 0.35)
            duration_frames = max(1, round(duration_seconds * self.FPS))

            audio_source_rel = f"assets/{audio_source.name}"
            selected_asset = asset_by_scene.get(scene_number, {})
            local_asset = self._copy_asset(
                selected_asset.get("path"),
                asset_dir / f"scene_{scene_number:03d}",
            )

            asset_payload: dict[str, Any]
            if local_asset is None:
                asset_payload = {
                    "kind": "color",
                    "color": self._scene_color(scene_number),
                }
            else:
                asset_payload = {
                    "kind": self._asset_kind(local_asset),
                    "src": f"assets/{local_asset.name}",
                }

            on_screen = str(
                raw_scene.get("on_screen_text")
                or raw_scene.get("visual")
                or f"Scene {index}"
            ).strip()[:240]

            caption = {
                "text": narration[:240],
                "startMs": round(cursor_seconds * 1000),
                "endMs": round((cursor_seconds + audio_duration) * 1000),
                "timestampMs": None,
                "confidence": None,
            }

            manifest_scenes.append(
                {
                    "scene": scene_number,
                    "durationFrames": duration_frames,
                    "asset": asset_payload,
                    "audioSrc": audio_source_rel,
                    "onScreenText": on_screen,
                    "motion": str(raw_scene.get("motion") or "slow_push_in"),
                    "transition": str(raw_scene.get("transition") or "cut"),
                    "captionStyle": str(raw_scene.get("caption_style") or raw_scene.get("captionStyle") or "standard"),
                    "caption": caption,
                }
            )
            subtitle_rows.append((cursor_seconds, cursor_seconds + audio_duration, narration))
            cursor_seconds += duration_frames / self.FPS

        captions = [scene["caption"] for scene in manifest_scenes]
        manifest = {
            "compositionId": self.COMPOSITION_ID,
            "width": self.WIDTH,
            "height": self.HEIGHT,
            "fps": self.FPS,
            "durationInFrames": sum(scene["durationFrames"] for scene in manifest_scenes),
            "scenes": manifest_scenes,
            "captions": captions,
            "outputPath": str(output_path),
            "publicDir": str(public_dir),
            "concurrency": max(1, int(settings.remotion_concurrency)),
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        write_srt(srt_path, subtitle_rows)
        captions_path.write_text(
            json.dumps(captions, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        await self._run_remotion(manifest_path)

        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RemotionRenderError("Remotion completed without producing a video file")

        duration_seconds = await probe_duration(output_path)
        return {
            "render_status": "completed",
            "render_engine": "remotion",
            "caption_engine": "remotion",
            "timeline_path": str(project_dir / "timeline.json"),
            "manifest_path": str(manifest_path),
            "subtitle_path": str(srt_path),
            "captions_path": str(captions_path),
            "output_path": str(output_path),
            "duration_seconds": round(duration_seconds, 2),
            "scene_count": len(manifest_scenes),
            "asset_count": len(asset_by_scene),
            "tts_provider": self.tts.name,
            "remotion_composition": self.COMPOSITION_ID,
        }

    async def _run_remotion(self, manifest_path: Path) -> None:
        renderer_dir = Path(settings.remotion_project_dir)
        command = [
            settings.remotion_node_bin,
            "render.mjs",
            "--input",
            str(manifest_path),
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=renderer_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            details = stderr.decode("utf-8", errors="replace")[-6000:]
            tail = stdout.decode("utf-8", errors="replace")[-2000:]
            raise RemotionRenderError(
                f"Remotion failed ({process.returncode}). stderr={details}; stdout={tail}"
            )

    @staticmethod
    def _copy_asset(source: Any, destination_base: Path) -> Path | None:
        if not source:
            return None
        source_path = Path(str(source))
        if not source_path.exists() or not source_path.is_file():
            return None

        suffix = source_path.suffix.lower()
        if suffix not in {
            ".mp4",
            ".mov",
            ".mkv",
            ".webm",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".avif",
        }:
            return None

        destination = destination_base.with_suffix(suffix)
        shutil.copy2(source_path, destination)
        return destination

    @staticmethod
    def _asset_kind(path: Path) -> str:
        if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}:
            return "video"
        return "image"

    @staticmethod
    def _scene_color(index: int) -> str:
        colors = [
            "#111827",
            "#1e293b",
            "#312e81",
            "#064e3b",
            "#7c2d12",
            "#27272a",
        ]
        return colors[(index - 1) % len(colors)]
