from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.media.factory import get_image_provider


class ThumbnailFactory:
    WIDTH = 1280
    HEIGHT = 720
    VARIANT_COUNT = 3
    VARIANT_AXIS = "text_presence"

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)

    @staticmethod
    def _font(size: int, bold: bool = False):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _wrap(text: str, max_chars: int = 24) -> list[str]:
        words = (text or "NEW VIDEO").split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines[:3]

    @staticmethod
    def _safe_text(value: str | None, limit: int) -> str:
        return " ".join((value or "").split())[:limit]

    def _draw_thumbnail(
        self,
        image: Image.Image,
        *,
        title: str,
        hook: str,
        variant_key: str,
    ) -> Image.Image:
        image = image.convert("RGB").resize((self.WIDTH, self.HEIGHT))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (42, 42, 1238, 678),
            radius=32,
            outline=(255, 255, 255),
            width=5,
        )

        title_font = self._font(70, bold=True)
        hook_font = self._font(30)
        title_lines = self._wrap(title)

        if variant_key == "variant_a":
            # Single controlled axis: remove the secondary hook text.
            y = 210
            for line in title_lines:
                draw.text(
                    (88, y),
                    line,
                    font=title_font,
                    fill=(255, 255, 255),
                    stroke_width=2,
                    stroke_fill=(0, 0, 0),
                )
                y += 84
        elif variant_key == "variant_b":
            # Single controlled axis: show hook only, preserving the same background.
            hook_text = self._safe_text(hook, 95) or "WATCH THE REASON"
            hook_lines = self._wrap(hook_text, max_chars=30)
            y = 235
            for line in hook_lines[:2]:
                draw.text(
                    (88, y),
                    line,
                    font=title_font,
                    fill=(255, 255, 255),
                    stroke_width=2,
                    stroke_fill=(0, 0, 0),
                )
                y += 84
        else:
            y = 145
            for line in title_lines:
                draw.text(
                    (88, y),
                    line,
                    font=title_font,
                    fill=(255, 255, 255),
                    stroke_width=2,
                    stroke_fill=(0, 0, 0),
                )
                y += 82
            draw.text(
                (90, 420),
                self._safe_text(hook, 95),
                font=hook_font,
                fill=(255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0),
            )

        return image

    async def _background(
        self,
        *,
        out_dir: Path,
        title: str,
        hook: str,
        provider_name: str | None,
        provider_config: dict | None,
    ) -> tuple[Image.Image, str]:
        provider_name = provider_name or settings.thumbnail_provider
        if provider_name not in {"pillow", "mock", "thumbnail_pillow"}:
            provider = get_image_provider(provider_name, provider_config)
            ai_path = out_dir / "thumbnail_source.png"
            ai = await provider.generate_scene_asset(
                prompt=(
                    "YouTube thumbnail background, high contrast, editorial, no text, "
                    f"based on: {title}. Hook: {hook}"
                ),
                output_path=str(ai_path),
                width=self.WIDTH,
                height=self.HEIGHT,
                duration_seconds=1.0,
                metadata={"thumbnail": True},
            )
            return Image.open(ai["path"]).convert("RGB"), provider.name

        image = Image.new("RGB", (self.WIDTH, self.HEIGHT), (2, 6, 23))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            (42, 42, 1238, 678),
            radius=32,
            fill=(15, 23, 42),
            outline=(71, 85, 105),
            width=5,
        )
        draw.ellipse((890, -80, 1410, 440), fill=(49, 46, 129))
        draw.ellipse((-190, 490, 360, 1040), fill=(6, 78, 59))
        return image, "thumbnail_pillow"

    async def create_variants(
        self,
        *,
        project_id: str,
        title: str,
        hook: str = "",
        provider_name: str | None = None,
        provider_config: dict | None = None,
        variants: Iterable[str] = ("control", "variant_a", "variant_b"),
    ) -> dict[str, Any]:
        out_dir = self.output_dir / project_id
        out_dir.mkdir(parents=True, exist_ok=True)

        background, provider = await self._background(
            out_dir=out_dir,
            title=title,
            hook=hook,
            provider_name=provider_name,
            provider_config=provider_config,
        )

        specs = {
            "control": {"label": "Control", "notes": "Current title plus hook text."},
            "variant_a": {"label": "Title only", "notes": "Removes the secondary hook line; same background."},
            "variant_b": {"label": "Hook only", "notes": "Removes the title line; same background."},
        }
        artifact_rows: list[dict[str, Any]] = []

        for key in variants:
            if key not in specs:
                raise ValueError(f"Unsupported thumbnail variant: {key}")
            suffix = "thumbnail.png" if key == "control" else f"thumbnail_{key}.png"
            path = out_dir / suffix
            rendered = self._draw_thumbnail(
                background.copy(),
                title=title,
                hook=hook,
                variant_key=key,
            )
            rendered.save(path, "PNG", optimize=True)
            artifact_rows.append(
                {
                    "variant_id": key,
                    "label": specs[key]["label"],
                    "axis": self.VARIANT_AXIS,
                    "notes": specs[key]["notes"],
                    "path": str(path),
                    "provider": provider,
                    "media_type": "image/png",
                }
            )

        manifest = {
            "version": "1",
            "project_id": project_id,
            "axis": self.VARIANT_AXIS,
            "single_axis_rule": True,
            "title": title,
            "hook": self._safe_text(hook, 240),
            "variants": artifact_rows,
        }
        manifest_path = out_dir / "thumbnail_variants.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "path": str(out_dir / "thumbnail.png"),
            "provider": provider,
            "status": "ready",
            "media_type": "image/png",
            "variant_axis": self.VARIANT_AXIS,
            "variants": artifact_rows,
            "manifest_path": str(manifest_path),
        }

    async def create(
        self,
        *,
        project_id: str,
        title: str,
        hook: str = "",
        provider_name: str | None = None,
        provider_config: dict | None = None,
    ) -> dict[str, Any]:
        return await self.create_variants(
            project_id=project_id,
            title=title,
            hook=hook,
            provider_name=provider_name,
            provider_config=provider_config,
        )
