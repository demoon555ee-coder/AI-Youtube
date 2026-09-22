from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.media.base import VisualAssetProvider


class MockVisualAssetProvider(VisualAssetProvider):
    """Deterministic local PNG generator for development and tests."""

    name = "mock_png"

    def _font(self, size: int, bold: bool = False):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _wrap(text: str, width_chars: int = 38) -> list[str]:
        words = (text or "AI visual").split()
        lines: list[str] = []
        current = ""
        for word in words:
            proposed = f"{current} {word}".strip()
            if len(proposed) > width_chars and current:
                lines.append(current)
                current = word
            else:
                current = proposed
        if current:
            lines.append(current)
        return lines[:4]

    async def generate_scene_asset(
        self,
        *,
        prompt: str,
        output_path: str,
        width: int = 1920,
        height: int = 1080,
        duration_seconds: float = 5.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = Path(output_path).with_suffix(".png")
        path.parent.mkdir(parents=True, exist_ok=True)

        palette = [(15, 23, 42), (30, 41, 59), (49, 46, 129), (6, 78, 59), (124, 45, 18), (39, 39, 42)]
        scene = int((metadata or {}).get("scene", 1))
        image = Image.new("RGB", (width, height), palette[(scene - 1) % len(palette)])
        draw = ImageDraw.Draw(image)
        draw.ellipse((width - 550, -100, width + 50, 500), fill=(255, 255, 255), width=0)
        draw.ellipse((-150, height - 420, 420, height + 150), fill=(255, 255, 255))
        draw.rectangle((80, 80, width - 80, height - 80), outline=(148, 163, 184), width=3)

        title_font = self._font(74, bold=True)
        meta_font = self._font(30)
        small_font = self._font(24)
        y = 355
        for line in self._wrap(prompt):
            draw.text((120, y), line, font=title_font, fill=(255, 255, 255))
            y += 90
        draw.text((120, 150), f"AI VISUAL · SCENE {scene}", font=meta_font, fill=(203, 213, 225))
        draw.text((120, height - 145), "Development preview asset — replace provider for production generation.", font=small_font, fill=(148, 163, 184))
        image.save(path, "PNG")
        return {
            "provider": self.name,
            "path": str(path),
            "media_type": "image/png",
            "duration_seconds": duration_seconds,
            "prompt": prompt,
        }
