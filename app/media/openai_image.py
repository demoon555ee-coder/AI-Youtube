from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.media.base import VisualAssetProvider
from app.media.url_guard import validate_remote_url
from app.resilience.http import request_with_retry
from app.config import settings


class OpenAIImageProvider(VisualAssetProvider):
    """Native OpenAI Images API adapter.

    Uses /images/generations and persists the returned image bytes locally.
    """

    name = "openai_image"

    def __init__(self, *, api_key: str, model: str = "gpt-image-2", base_url: str = "https://api.openai.com/v1", timeout_seconds: int = 180):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI image generation")
        self.api_key = api_key
        self.model = model
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
        # Current OpenAI image API accepts a constrained set of generated image sizes.
        size = _nearest_size(width, height)
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            ),
                max_retries=settings.llm_max_retries,
            )
            response.raise_for_status()
            data = response.json()
            item = (data.get("data") or [{}])[0]
            if item.get("b64_json"):
                content = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                image_url = validate_remote_url(str(item["url"]))
                image = await client.get(image_url)
                image.raise_for_status()
                content = image.content
            else:
                raise ValueError("OpenAI image response did not contain image data")

        path = Path(output_path).with_suffix(".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "provider": self.name,
            "path": str(path),
            "media_type": "image/png",
            "duration_seconds": duration_seconds,
            "prompt": prompt,
            "usage": data.get("usage", {}),
            "revised_prompt": item.get("revised_prompt"),
        }


def _nearest_size(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio > 1.5:
        return "1536x1024"
    if ratio < 0.75:
        return "1024x1536"
    return "1024x1024"
