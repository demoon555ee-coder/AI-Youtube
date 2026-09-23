from __future__ import annotations

import asyncio
import base64
import io
import random
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.config import settings
from app.media.base import VisualAssetProvider
from app.resilience.http import request_with_retry


class RunwayVideoProvider(VisualAssetProvider):
    """Runway Dev async text/image-to-video adapter."""

    name = "runway"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.dev.runwayml.com/v1",
        model: str = "gen4.5",
        poll_seconds: float = 5.0,
        timeout_seconds: int = 900,
    ):
        if not api_key:
            raise RuntimeError("RUNWAY_API_SECRET or VIDEO_API_KEY is required for Runway")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model or "gen4.5"
        self.poll_seconds = max(5.0, poll_seconds)
        self.timeout_seconds = max(30, timeout_seconds)
        self.api_version = "2024-11-06"

    async def generate_scene_asset(
        self,
        *,
        prompt: str,
        output_path: str,
        width: int = 1280,
        height: int = 720,
        duration_seconds: float = 5.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        image_path = str(metadata.get("image_path") or metadata.get("source_image") or "").strip()
        image_data = self._image_data_uri(image_path) if image_path else None

        ratio = "1280:720" if width >= height else "720:1280"
        duration = max(2, min(10, int(round(duration_seconds or 5))))

        payload: dict[str, Any] = {
            "model": self.model,
            "promptText": prompt,
            "ratio": ratio,
            "duration": duration,
        }
        if image_data:
            payload["promptImage"] = image_data

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": self.api_version,
        }

        async with httpx.AsyncClient(timeout=180) as client:
            response = await request_with_retry(
                lambda: client.post(f"{self.base_url}/image_to_video", json=payload, headers=headers),
                max_retries=settings.llm_max_retries,
            )
            response.raise_for_status()
            task = response.json()

            task_id = task.get("id")
            if not task_id:
                raise ValueError("Runway response did not contain a task id")

            deadline = asyncio.get_running_loop().time() + self.timeout_seconds
            while True:
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Runway task timed out: {task_id}")

                status_response = await request_with_retry(
                    lambda: client.get(
                        f"{self.base_url}/tasks/{task_id}",
                        headers={"Authorization": f"Bearer {self.api_key}", "X-Runway-Version": self.api_version},
                    ),
                    max_retries=settings.llm_max_retries,
                )
                status_response.raise_for_status()
                task = status_response.json()
                status = str(task.get("status") or "PENDING").upper()

                if status == "SUCCEEDED":
                    outputs = task.get("output") or []
                    if not outputs:
                        raise ValueError("Runway task succeeded without an output URL")
                    download_url = self._validate_output_url(str(outputs[0]))
                    media = await request_with_retry(
                        lambda: client.get(download_url),
                        max_retries=settings.llm_max_retries,
                    )
                    media.raise_for_status()
                    path = Path(output_path).with_suffix(".mp4")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(media.content)
                    return {
                        "provider": self.name,
                        "path": str(path),
                        "media_type": "video/mp4",
                        "duration_seconds": float(duration),
                        "prompt": prompt,
                        "external_job_id": str(task_id),
                        "status": "completed",
                        "output_url": download_url,
                        "usage": task.get("usage") or {},
                    }

                if status in {"FAILED", "CANCELED"}:
                    detail = task.get("failure") or task.get("failureCode") or status
                    raise RuntimeError(f"Runway video task failed: {detail}")

                jitter = random.uniform(0.8, 1.2)
                await asyncio.sleep(self.poll_seconds * jitter)

    @staticmethod
    def _image_data_uri(image_path: str) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Runway source image does not exist: {image_path}")

        raw = path.read_bytes()
        mime = "image/png"
        if len(raw) <= 5 * 1024 * 1024:
            if path.suffix.lower() in {".jpg", ".jpeg"}:
                mime = "image/jpeg"
            return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")

        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGB")
            max_dim = max(image.size)
            scale = min(1.0, 2048 / max_dim)
            if scale < 1.0:
                image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
            buffer = io.BytesIO()
            quality = 85
            while True:
                buffer.seek(0)
                buffer.truncate(0)
                image.save(buffer, format="JPEG", quality=quality, optimize=True)
                if buffer.tell() <= 5 * 1024 * 1024 or quality <= 60:
                    break
                quality -= 5
            raw = buffer.getvalue()

        return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _validate_output_url(value: str) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            raise ValueError("Runway output URL must use https and include a hostname")
        if not (
            host.endswith(".cloudfront.net")
            or host.endswith(".runwayml.com")
            or host == "runwayml.com"
        ):
            raise ValueError(f"Runway output URL host is not allowed: {host}")
        return value
