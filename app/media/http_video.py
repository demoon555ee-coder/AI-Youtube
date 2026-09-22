from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.media.base import VisualAssetProvider
from app.media.url_guard import validate_remote_url
from app.resilience.http import request_with_retry
from app.config import settings


class HTTPVideoProvider(VisualAssetProvider):
    """Generic async video-generation adapter.

    Provider contract:
      POST endpoint -> {id|job_id, status_url?, download_url?, status?}
      GET status_url -> {status, download_url?, output_url?}
    Completed jobs can also return a direct URL from the POST response.
    """

    name = "http_video"

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str = "",
        model: str = "",
        poll_seconds: float = 5.0,
        timeout_seconds: int = 900,
        allowed_hosts: set[str] | None = None,
        forward_auth_to_download: bool = False,
    ):
        if not endpoint:
            raise RuntimeError("VIDEO_ENDPOINT is required for http_video provider")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.poll_seconds = max(0.5, poll_seconds)
        self.timeout_seconds = max(5, timeout_seconds)
        default_host = urlparse(self.endpoint).hostname
        self.allowed_hosts = set(allowed_hosts or set())
        if default_host:
            self.allowed_hosts.add(default_host)
        self.forward_auth_to_download = forward_auth_to_download

    async def recover_existing_job(
        self,
        *,
        status_url: str,
        output_path: str,
        external_job_id: str | None = None,
        output_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        metadata = metadata or {}
        download_url = validate_remote_url(str(output_url), allowed_hosts=self.allowed_hosts) if output_url else None
        status_url = validate_remote_url(str(status_url), allowed_hosts=self.allowed_hosts)
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        async with httpx.AsyncClient(timeout=180) as client:
            status = "processing"
            data: dict[str, Any] = {}
            while not download_url and status not in {"failed", "cancelled", "error"}:
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Video recovery timed out for job {external_job_id}")
                poll = await request_with_retry(lambda: client.get(status_url, headers=headers), max_retries=settings.llm_max_retries)
                poll.raise_for_status()
                data = poll.json()
                status = str(data.get("status") or data.get("state") or "processing").lower()
                download_url = data.get("download_url") or data.get("output_url")
                if download_url:
                    download_url = validate_remote_url(str(download_url), allowed_hosts=self.allowed_hosts)
                if not download_url:
                    await asyncio.sleep(self.poll_seconds)
            if status in {"failed", "cancelled", "error"}:
                raise RuntimeError(str(data.get("error") or f"Video generation failed: {status}"))
            if not download_url:
                raise ValueError("Recovered video job completed without download_url")
            download_headers = headers if self.forward_auth_to_download else {}
            media = await request_with_retry(lambda: client.get(download_url, headers=download_headers), max_retries=settings.llm_max_retries)
            media.raise_for_status()
            path = Path(output_path).with_suffix(".mp4")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(media.content)
        return {"provider": self.name, "path": str(path), "media_type": "video/mp4", "external_job_id": external_job_id, "status_url": status_url, "download_url": download_url, "status": "completed", "usage": data.get("usage", {})}

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
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        metadata = metadata or {}
        idempotency_key = metadata.get("idempotency_key")
        if idempotency_key:
            headers["Idempotency-Key"] = str(idempotency_key)
        payload: dict[str, Any] = {
            "prompt": prompt,
            "duration": duration_seconds,
            "size": f"{width}x{height}",
        }
        if self.model:
            payload["model"] = self.model

        async with httpx.AsyncClient(timeout=180) as client:
            response = await request_with_retry(
                lambda: client.post(self.endpoint, json=payload, headers=headers),
                max_retries=settings.llm_max_retries,
            )
            response.raise_for_status()
            data = response.json()
            status_url = data.get("status_url") or data.get("poll_url")
            download_url = data.get("download_url") or data.get("output_url")
            if status_url:
                status_url = validate_remote_url(str(status_url), allowed_hosts=self.allowed_hosts)
            if download_url:
                download_url = validate_remote_url(str(download_url), allowed_hosts=self.allowed_hosts)
            job_id = data.get("id") or data.get("job_id")
            status = str(data.get("status") or "queued").lower()
            callback = metadata.get("on_submitted")
            if callback and job_id:
                await callback({
                    "provider": self.name,
                    "external_job_id": str(job_id),
                    "status_url": status_url,
                    "download_url": download_url,
                    "status": status,
                    "output_path": str(Path(output_path).with_suffix(".mp4")),
                    "scene": metadata.get("scene", 0),
                    "idempotency_key": idempotency_key,
                })

            deadline = asyncio.get_running_loop().time() + self.timeout_seconds
            while not download_url and status not in {"failed", "cancelled", "error"}:
                if not status_url:
                    raise ValueError("Video provider response requires status_url/poll_url or download_url")
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"Video generation timed out for job {job_id}")
                await asyncio.sleep(self.poll_seconds)
                poll = await request_with_retry(
                    lambda: client.get(status_url, headers=headers),
                    max_retries=settings.llm_max_retries,
                )
                poll.raise_for_status()
                data = poll.json()
                status = str(data.get("status") or data.get("state") or "processing").lower()
                download_url = data.get("download_url") or data.get("output_url")
                if download_url:
                    download_url = validate_remote_url(str(download_url), allowed_hosts=self.allowed_hosts)

            if status in {"failed", "cancelled", "error"}:
                raise RuntimeError(str(data.get("error") or f"Video generation failed: {status}"))
            if not download_url:
                raise ValueError("Video provider completed without download_url")

            download_headers = headers if self.forward_auth_to_download else {}
            media = await request_with_retry(
                lambda: client.get(download_url, headers=download_headers),
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
            "duration_seconds": duration_seconds,
            "prompt": prompt,
            "external_job_id": job_id,
            "status_url": status_url,
            "download_url": download_url,
            "status": "completed",
            "usage": data.get("usage", {}),
        }
