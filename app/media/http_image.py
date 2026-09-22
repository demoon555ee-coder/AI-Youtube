from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.media.base import VisualAssetProvider
from app.media.url_guard import validate_remote_url


class HTTPImageProvider(VisualAssetProvider):
    """Small adapter for an image endpoint that returns b64_json or a URL."""

    name = "http_image"

    def __init__(self, *, endpoint: str, api_key: str = "", model: str = "", allowed_hosts: set[str] | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        from urllib.parse import urlparse
        default_host = urlparse(self.endpoint).hostname
        self.allowed_hosts = set(allowed_hosts or set())
        if default_host:
            self.allowed_hosts.add(default_host)

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
        payload: dict[str, Any] = {
            "prompt": prompt,
            "size": f"{width}x{height}",
        }
        if self.model:
            payload["model"] = self.model
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if metadata and metadata.get("idempotency_key"):
            headers["Idempotency-Key"] = str(metadata["idempotency_key"])
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            item = (data.get("data") or [{}])[0]
            if item.get("b64_json"):
                content = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                image_url = validate_remote_url(item["url"], allowed_hosts=self.allowed_hosts)
                image_response = await client.get(image_url)
                image_response.raise_for_status()
                content = image_response.content
            else:
                raise ValueError("Image provider response did not contain b64_json or url")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "provider": self.name,
            "path": str(path),
            "media_type": "image",
            "duration_seconds": duration_seconds,
            "prompt": prompt,
        }
