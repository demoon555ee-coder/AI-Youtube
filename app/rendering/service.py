from __future__ import annotations

import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from app.tts import get_tts


class RenderService:
    def __init__(self, output_dir: str, tts_provider: str | None = None, tts_config: dict | None = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tts = get_tts(tts_provider, tts_config)

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
        asset_by_scene = {int(a["scene"]): a for a in (assets or [])}

        project_dir = self.output_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        timeline_path = project_dir / "timeline.json"
        output_path = project_dir / "final.mp4"
        srt_path = project_dir / "subtitles.srt"
        timeline_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")

        with tempfile.TemporaryDirectory(dir=project_dir) as tmp:
            tmp_dir = Path(tmp)
            scene_files: list[Path] = []
            subtitle_rows: list[tuple[float, float, str]] = []
            cursor = 0.0

            for index, scene in enumerate(scenes, start=1):
                narration = _safe_text(scene.get("narration") or scene.get("visual") or "")
                requested_duration = max(float(scene.get("duration", 1)), 0.5)
                audio_path = tmp_dir / f"voice_{index}.wav"
                await synthesize_with_chunking(
                    self.tts, narration, audio_path, language=language, voice=voice
                )
                audio_duration = await probe_duration(audio_path)
                duration = max(requested_duration, audio_duration + 0.35)

                display_text = _safe_text(scene.get("on_screen_text") or scene.get("visual") or f"Scene {index}")
                scene_txt = tmp_dir / f"scene_{index}.txt"
                scene_txt.write_text(display_text, encoding="utf-8")
                scene_path = tmp_dir / f"scene_{index}.mp4"

                asset_path = asset_by_scene.get(index, {}).get("path")
                asset_exists = bool(asset_path and Path(str(asset_path)).exists())
                is_video_asset = asset_exists and Path(str(asset_path)).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
                if asset_exists and is_video_asset:
                    inputs = ["-stream_loop", "-1", "-i", str(asset_path)]
                    video_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                elif asset_exists:
                    inputs = ["-loop", "1", "-i", str(asset_path)]
                    video_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                else:
                    inputs = ["-f", "lavfi", "-i", f"color=c={_scene_color(index)}:s=1920x1080:r=30"]
                    video_filter = "format=yuv420p"
                font_file = _font_file()
                drawtext = (
                    f"drawtext=fontfile={_escape_filter_path(font_file)}:"
                    f"textfile={_escape_filter_path(str(scene_txt))}:fontcolor=white:fontsize=64:"
                    "box=1:boxcolor=black@0.45:boxborderw=18:"
                    "x=(w-text_w)/2:y=(h-text_h)/2"
                )
                vf = f"{video_filter},{drawtext}"
                await _run([
                    "ffmpeg", "-y", *inputs,
                    "-i", str(audio_path),
                    "-t", f"{duration:.3f}",
                    "-vf", vf,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-shortest",
                    str(scene_path),
                ])
                scene_files.append(scene_path)
                subtitle_rows.append((cursor, cursor + audio_duration, narration))
                cursor += duration

            concat_file = tmp_dir / "concat.txt"
            concat_file.write_text("\n".join(f"file '{p}'" for p in scene_files) + "\n", encoding="utf-8")
            await _run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c", "copy", str(output_path),
            ])

            write_srt(srt_path, subtitle_rows)
            captioned_path = project_dir / "final_captioned.mp4"
            subtitle_filter = (
                f"subtitles={_escape_filter_path(str(srt_path))}:"
                "force_style='FontName=DejaVu Sans,FontSize=22,"
                "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=40'"
            )
            await _run([
                "ffmpeg", "-y", "-i", str(output_path), "-vf", subtitle_filter,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy",
                str(captioned_path),
            ])
            captioned_path.replace(output_path)

        duration_seconds = await probe_duration(output_path)
        return {
            "render_status": "completed",
            "timeline_path": str(timeline_path),
            "subtitle_path": str(srt_path),
            "output_path": str(output_path),
            "duration_seconds": round(duration_seconds, 2),
            "scene_count": len(scenes),
            "asset_count": len(asset_by_scene),
            "tts_provider": self.tts.name,
        }


def split_text_for_tts(text: str, max_chars: int = 3800) -> list[str]:
    cleaned = _safe_text(text)
    if len(str(text)) <= max_chars:
        return [str(text)]
    words = str(text).split()
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [" "]


async def synthesize_with_chunking(tts, text: str, output_path: Path, *, language: str, voice: str | None) -> None:
    chunks = split_text_for_tts(text)
    if len(chunks) == 1:
        await tts.synthesize(chunks[0], output_path, language=language, voice=voice)
        return
    with tempfile.TemporaryDirectory(dir=output_path.parent) as tmp:
        tmp_dir = Path(tmp)
        chunk_paths: list[Path] = []
        for idx, chunk in enumerate(chunks, start=1):
            chunk_path = tmp_dir / f"chunk_{idx:03d}.wav"
            await tts.synthesize(chunk, chunk_path, language=language, voice=voice)
            chunk_paths.append(chunk_path)
        concat = tmp_dir / "concat.txt"
        concat.write_text("\n".join(f"file '{p}'" for p in chunk_paths) + "\n", encoding="utf-8")
        await _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c:a", "pcm_s16le", str(output_path),
        ])


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


async def _run(command: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({process.returncode}): {stderr.decode('utf-8', errors='replace')[-4000:]}")


def write_srt(path: Path, rows: list[tuple[float, float, str]]) -> None:
    blocks = []
    for index, (start, end, text) in enumerate(rows, 1):
        blocks.append(f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")


def format_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _safe_text(value: str) -> str:
    value = re.sub(r"[\r\n]+", " ", str(value))
    return value[:240]


def _font_file() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return candidates[0]


def _escape_filter_path(value: str) -> str:
    return value.replace("\\", "/").replace(":", "\\\\:").replace("'", "\\'")


def _scene_color(index: int) -> str:
    colors = ["0x111827", "0x1e293b", "0x312e81", "0x064e3b", "0x7c2d12", "0x27272a"]
    return colors[(index - 1) % len(colors)]
