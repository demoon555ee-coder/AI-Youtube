from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.media.base import VisualAssetProvider
from app.resilience.http import request_with_retry


class StabilityImageProvider(VisualAssetProvider):
    """Stability AI (Stable Image) adapter.

    The Stability v2beta API expects multipart/form-data and returns a JSON
    body with a base64-encoded image. The result is persisted locally and the
    returned metadata mirrors the other VisualAssetProvider implementations.
    """

    name = "stability_image"

    def __init__(self, *, api_key: str, base_url: str = "https://api.stability.ai", timeout_seconds: int = 180):
        if not api_key:
            raise RuntimeError("STABILITY_API_KEY is required for Stability image generation")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

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
        aspect_ratio = _nearest_aspect_ratio(width, height)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(
                    f"{self.base_url}/v2beta/stable-image/generate/core",
                    headers=headers,
                    files={
                        "prompt": (None, prompt),
                        "aspect_ratio": (None, aspect_ratio),
                        "output_format": (None, "png"),
                    },
                ),
                max_retries=settings.llm_max_retries,
            )
            response.raise_for_status()
            data = response.json()
            image_b64 = data.get("image")
            if not image_b64:
                raise ValueError("Stability image response did not contain image data")
            content = base64.b64decode(image_b64)

        path = Path(output_path).with_suffix(".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "provider": self.name,
            "path": str(path),
            "media_type": "image/png",
            "duration_seconds": duration_seconds,
            "prompt": prompt,
            "usage": {},
            "revised_prompt": data.get("seed"),
        }


def _nearest_aspect_ratio(width: int, height: int) -> str:
    """Map requested dimensions to the closest Stability aspect ratio."""
    ratio = width / max(height, 1)
    if ratio >= 2.0:
        return "21:9"
    if ratio >= 1.4:
        return "16:9"
    if ratio >= 1.1:
        return "3:2"
    if ratio >= 0.9:
        return "1:1"
    if ratio >= 0.7:
        return "2:3"
    if ratio >= 0.5:
        return "9:16"
    return "9:21"