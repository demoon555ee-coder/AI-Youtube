from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.media.factory import get_image_provider


class ThumbnailFactory:
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

    async def create(self, *, project_id: str, title: str, hook: str = "", provider_name: str | None = None, provider_config: dict | None = None) -> dict[str, Any]:
        out_dir = self.output_dir / project_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "thumbnail.png"

        provider_name = provider_name or settings.thumbnail_provider
        if provider_name not in {"pillow", "mock", "thumbnail_pillow"}:
            provider = get_image_provider(provider_name, provider_config)
            ai_path = out_dir / "thumbnail_source.png"
            ai = await provider.generate_scene_asset(
                prompt=f"YouTube thumbnail background, high contrast, editorial, no text, based on: {title}. Hook: {hook}",
                output_path=str(ai_path), width=1280, height=720, duration_seconds=1.0, metadata={"thumbnail": True},
            )
            background = Image.open(ai["path"]).convert("RGB").resize((1280, 720))
            image = background
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((42, 42, 1238, 678), radius=32, outline=(255, 255, 255), width=5)
            title_font = self._font(70, bold=True)
            hook_font = self._font(30)
            y = 145
            for line in self._wrap(title):
                draw.text((88, y), line, font=title_font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
                y += 82
            draw.text((90, 420), (hook or "")[:95], font=hook_font, fill=(255, 255, 255), stroke_width=1, stroke_fill=(0, 0, 0))
            image.save(path, "PNG", optimize=True)
            return {"path": str(path), "provider": provider.name, "source_provider": provider.name, "status": "ready", "media_type": "image/png"}

        image = Image.new("RGB", (1280, 720), (2, 6, 23))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((42, 42, 1238, 678), radius=32, fill=(15, 23, 42), outline=(71, 85, 105), width=5)
        draw.ellipse((890, -80, 1410, 440), fill=(49, 46, 129))
        draw.ellipse((-190, 490, 360, 1040), fill=(6, 78, 59))

        title_font = self._font(70, bold=True)
        hook_font = self._font(30)
        small_font = self._font(22)
        y = 145
        for line in self._wrap(title):
            draw.text((88, y), line, font=title_font, fill=(255, 255, 255))
            y += 82
        draw.text((90, 420), (hook or "AI-generated content draft")[:95], font=hook_font, fill=(203, 213, 225))
        draw.text((90, 620), "AI thumbnail draft · generate a branded variant in production", font=small_font, fill=(148, 163, 184))
        image.save(path, "PNG", optimize=True)
        return {"path": str(path), "provider": "thumbnail_pillow", "status": "ready", "media_type": "image/png"}
