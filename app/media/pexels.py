from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.resilience.http import request_with_retry
from app.media.base import VisualAssetProvider


PEXELS_API_BASE = "https://api.pexels.com/v1"
_ALLOWED_IMAGE_HOSTS = {"images.pexels.com"}
_ALLOWED_VIDEO_HOSTS = {"player.vimeo.com", "videos.pexels.com"}


class _PexelsSearchCache:
    _items: dict[tuple[str, str, str, int], tuple[float, dict[str, Any]]] = {}

    @classmethod
    def get(cls, key: tuple[str, str, str, int], ttl: int) -> dict[str, Any] | None:
        item = cls._items.get(key)
        if not item:
            return None
        created_at, payload = item
        if time.monotonic() - created_at > max(0, ttl):
            cls._items.pop(key, None)
            return None
        return payload

    @classmethod
    def put(cls, key: tuple[str, str, str, int], payload: dict[str, Any]) -> None:
        cls._items[key] = (time.monotonic(), payload)


class _PexelsBaseProvider(VisualAssetProvider):
    api_base = PEXELS_API_BASE

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = PEXELS_API_BASE,
        timeout_seconds: int = 120,
        cache_ttl_seconds: int = 86400,
    ):
        if not api_key:
            raise RuntimeError("PEXELS_API_KEY is required for the Pexels provider")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": self.api_key}

    @staticmethod
    def _orientation(width: int, height: int) -> str:
        if width > height * 1.12:
            return "landscape"
        if height > width * 1.12:
            return "portrait"
        return "square"

    @staticmethod
    def _normalize_query(prompt: str) -> str:
        query = " ".join(prompt.strip().split())
        if not query:
            raise ValueError("Pexels search query cannot be empty")
        return query[:200]

    @staticmethod
    def _validate_download_url(value: str, allowed_hosts: set[str]) -> str:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in allowed_hosts:
            raise ValueError(f"Pexels media URL host is not allowed: {host or 'missing'}")
        return value

    @staticmethod
    def _api_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            detail = body.get("error") or body.get("message") or body.get("detail")
            if detail:
                return f"Pexels API request failed ({response.status_code}): {str(detail)[:500]}"
        except ValueError:
            pass
        return f"Pexels API request failed ({response.status_code})"

    async def _get_json(self, client: httpx.AsyncClient, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        response = await request_with_retry(
            lambda: client.get(url, params=params, headers=self.headers),
            max_retries=settings.llm_max_retries,
        )
        if response.is_error:
            raise RuntimeError(self._api_error(response))
        return response.json()

    async def _download(self, client: httpx.AsyncClient, url: str, *, allowed_hosts: set[str]) -> bytes:
        safe_url = self._validate_download_url(url, allowed_hosts)
        response = await request_with_retry(
            lambda: client.get(safe_url),
            max_retries=settings.llm_max_retries,
        )
        response.raise_for_status()
        return response.content


class PexelsPhotoProvider(_PexelsBaseProvider):
    """Pexels photo search provider for stock stills and fallback visual assets."""

    name = "pexels_photo"

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
        del duration_seconds
        metadata = metadata or {}
        query = self._normalize_query(str(metadata.get("search_query") or prompt))
        orientation = str(metadata.get("orientation") or self._orientation(width, height))
        locale = str(metadata.get("locale") or "en-US")
        cache_key = ("photo", query.lower(), orientation, 12)

        cached = _PexelsSearchCache.get(cache_key, self.cache_ttl_seconds)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = cached or await self._get_json(
                client,
                f"{self.base_url}/search",
                params={
                    "query": query,
                    "orientation": orientation,
                    "locale": locale,
                    "per_page": 12,
                },
            )
            if cached is None:
                _PexelsSearchCache.put(cache_key, payload)

            photos = payload.get("photos") or []
            if not photos:
                raise RuntimeError(f"Pexels returned no photos for query: {query}")

            photo = photos[0]
            src = photo.get("src") or {}
            media_url = src.get("landscape" if orientation == "landscape" else orientation) or src.get("large2x") or src.get("original")
            if not media_url:
                raise RuntimeError("Pexels photo result did not contain a usable media URL")

            media = await self._download(client, str(media_url), allowed_hosts=_ALLOWED_IMAGE_HOSTS)

        source_suffix = Path(urlparse(str(media_url)).path).suffix.lower()
        image_suffix = source_suffix if source_suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"
        path = Path(output_path).with_suffix(image_suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(media)
        media_type = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"
        }[image_suffix]

        photographer = str(photo.get("photographer") or "Unknown")
        photographer_url = str(photo.get("photographer_url") or "")
        pexels_url = str(photo.get("url") or "")

        return {
            "provider": self.name,
            "path": str(path),
            "media_type": media_type,
            "status": "completed",
            "external_job_id": str(photo.get("id") or ""),
            "source_url": pexels_url,
            "attribution": {
                "provider": "Pexels",
                "provider_url": "https://www.pexels.com/",
                "media_url": pexels_url,
                "creator": photographer,
                "creator_url": photographer_url,
                "text": f"Photo by {photographer} on Pexels",
            },
            "search_query": query,
            "width": photo.get("width"),
            "height": photo.get("height"),
        }


class PexelsVideoProvider(_PexelsBaseProvider):
    """Pexels video search provider optimized for stock B-roll."""

    name = "pexels_video"

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
        metadata = metadata or {}
        query = self._normalize_query(str(metadata.get("search_query") or prompt))
        orientation = str(metadata.get("orientation") or self._orientation(width, height))
        locale = str(metadata.get("locale") or "en-US")
        target_duration = max(1.0, float(duration_seconds or 5.0))
        cache_key = ("video", query.lower(), orientation, 12)

        cached = _PexelsSearchCache.get(cache_key, self.cache_ttl_seconds)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            payload = cached or await self._get_json(
                client,
                f"{self.base_url}/videos/search",
                params={
                    "query": query,
                    "orientation": orientation,
                    "size": "medium",
                    "locale": locale,
                    "per_page": 12,
                },
            )
            if cached is None:
                _PexelsSearchCache.put(cache_key, payload)

            videos = payload.get("videos") or []
            if not videos:
                raise RuntimeError(f"Pexels returned no videos for query: {query}")

            video = self._select_video(videos, width=width, height=height, duration=target_duration)
            video_file = self._select_file(video.get("video_files") or [], width=width, height=height)
            if not video_file or not video_file.get("link"):
                raise RuntimeError("Pexels video result did not contain a usable MP4 file")

            media_url = str(video_file["link"])
            media = await self._download(client, media_url, allowed_hosts=_ALLOWED_VIDEO_HOSTS)

        path = Path(output_path).with_suffix(".mp4")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(media)

        user = video.get("user") or {}
        creator = str(user.get("name") or "Unknown")
        creator_url = str(user.get("url") or "")
        pexels_url = str(video.get("url") or "")

        return {
            "provider": self.name,
            "path": str(path),
            "media_type": "video/mp4",
            "status": "completed",
            "external_job_id": str(video.get("id") or ""),
            "source_url": pexels_url,
            "attribution": {
                "provider": "Pexels",
                "provider_url": "https://www.pexels.com/",
                "media_url": pexels_url,
                "creator": creator,
                "creator_url": creator_url,
                "text": f"Video by {creator} on Pexels",
            },
            "search_query": query,
            "source_duration_seconds": video.get("duration"),
            "selected_width": video_file.get("width"),
            "selected_height": video_file.get("height"),
            "selected_quality": video_file.get("quality"),
        }

    @staticmethod
    def _select_video(videos: list[dict[str, Any]], *, width: int, height: int, duration: float) -> dict[str, Any]:
        target_ratio = width / max(1, height)

        def score(video: dict[str, Any]) -> tuple[float, float, float]:
            vw = float(video.get("width") or 0)
            vh = float(video.get("height") or 0)
            ratio = vw / vh if vw and vh else target_ratio
            ratio_delta = abs(ratio - target_ratio)
            duration_delta = 0.0 if float(video.get("duration") or 0) >= duration else duration - float(video.get("duration") or 0)
            resolution = -(vw * vh)
            return (ratio_delta, duration_delta, resolution)

        return min(videos, key=score)

    @staticmethod
    def _select_file(files: list[dict[str, Any]], *, width: int, height: int) -> dict[str, Any] | None:
        target_pixels = max(1, width * height)
        mp4_files = [
            item for item in files
            if str(item.get("file_type") or "").lower() == "video/mp4"
            and item.get("link")
            and item.get("width")
            and item.get("height")
        ]
        if not mp4_files:
            return None

        def score(item: dict[str, Any]) -> tuple[float, float, float]:
            pixels = float(item["width"]) * float(item["height"])
            quality_penalty = 0.0 if str(item.get("quality")).lower() == "hd" else 1.0
            return (abs(pixels - target_pixels) / target_pixels, quality_penalty, -pixels)

        return min(mp4_files, key=score)
