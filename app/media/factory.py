from __future__ import annotations

import os

from app.config import settings
from app.media.base import VisualAssetProvider
from app.media.http_image import HTTPImageProvider
from app.media.http_video import HTTPVideoProvider
from app.media.mock import MockVisualAssetProvider
from app.media.openai_image import OpenAIImageProvider
from app.media.pexels import PexelsPhotoProvider, PexelsVideoProvider
from app.media.runway_video import RunwayVideoProvider
from app.media.stability_image import StabilityImageProvider


def get_visual_provider(provider_name: str | None = None, config: dict | None = None) -> VisualAssetProvider:
    cfg = config or {}
    name = provider_name or settings.visual_provider
    kind = str(cfg.get("kind") or name)

    if name == "mock_png" or kind == "mock_png":
        return MockVisualAssetProvider()
    if name == "openai_image" or kind == "openai_image":
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else (str(cfg.get("api_key") or settings.image_api_key or settings.llm_api_key) or "")
        endpoint = str(cfg.get("base_url") or cfg.get("endpoint") or settings.image_endpoint or "https://api.openai.com/v1")
        model = str(cfg.get("model") or settings.image_model or "gpt-image-2")
        return OpenAIImageProvider(api_key=api_key, base_url=endpoint, model=model)
    if name == "stability_image" or kind == "stability_image":
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else (str(cfg.get("api_key") or settings.stability_api_key) or "")
        endpoint = str(cfg.get("base_url") or cfg.get("endpoint") or settings.image_endpoint or "https://api.stability.ai")
        return StabilityImageProvider(api_key=api_key, base_url=endpoint)
    if name == "pexels_photo" or kind == "pexels_photo":
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.pexels_api_key)
        return PexelsPhotoProvider(
            api_key=api_key,
            base_url=str(cfg.get("base_url") or "https://api.pexels.com/v1"),
            timeout_seconds=settings.readiness_timeout_seconds * 40,
            cache_ttl_seconds=int(cfg.get("cache_ttl_seconds", 86400)),
        )
    if name == "http_image" or kind == "http_image":
        endpoint = str(cfg.get("endpoint") or settings.visual_endpoint or settings.image_endpoint)
        if not endpoint:
            raise RuntimeError("VISUAL_ENDPOINT or IMAGE_ENDPOINT is required for http_image provider")
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.visual_api_key or settings.image_api_key)
        allowed_hosts = set(str(x).strip() for x in (cfg.get("allowed_hosts") or []) if str(x).strip())
        return HTTPImageProvider(endpoint=endpoint, api_key=api_key, model=str(cfg.get("model") or settings.visual_model or settings.image_model), allowed_hosts=allowed_hosts)
    if name == "mock_video" or kind == "mock_video":
        from app.media.mock_video import MockVideoProvider
        return MockVideoProvider()
    if name == "pexels_video" or kind == "pexels_video":
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.pexels_api_key)
        return PexelsVideoProvider(
            api_key=api_key,
            base_url=str(cfg.get("base_url") or "https://api.pexels.com/v1"),
            timeout_seconds=settings.readiness_timeout_seconds * 40,
            cache_ttl_seconds=int(cfg.get("cache_ttl_seconds", 86400)),
        )
    if name == "runway" or kind == "runway":
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.runway_api_key or settings.video_api_key or os.getenv("RUNWAY_API_KEY", "") or os.getenv("RUNWAYML_API_SECRET", "") or os.getenv("RUNWAY_API_SECRET", "") or os.getenv("RUNWAY_API", ""))
        return RunwayVideoProvider(
            api_key=api_key,
            base_url=str(cfg.get("base_url") or settings.video_endpoint or "https://api.dev.runwayml.com/v1"),
            model=str(cfg.get("model") or settings.video_model or "gen4.5"),
            poll_seconds=settings.video_poll_seconds,
            timeout_seconds=settings.video_timeout_seconds,
        )
    if name == "http_video" or kind == "http_video":
        endpoint = str(cfg.get("endpoint") or settings.video_endpoint)
        api_key = os.getenv(str(cfg.get("api_key_env", "")), "") if cfg.get("api_key_env") else str(cfg.get("api_key") or settings.video_api_key)
        allowed_hosts = set(str(x).strip() for x in (cfg.get("allowed_hosts") or []) if str(x).strip())
        return HTTPVideoProvider(
            endpoint=endpoint,
            api_key=api_key,
            model=str(cfg.get("model") or settings.video_model),
            poll_seconds=settings.video_poll_seconds,
            timeout_seconds=settings.video_timeout_seconds,
            allowed_hosts=allowed_hosts,
            forward_auth_to_download=bool(cfg.get("forward_auth_to_download", False)),
        )
    raise ValueError(f"Unknown visual provider: {name}")


def get_image_provider(provider_name: str | None = None, config: dict | None = None) -> VisualAssetProvider:
    cfg = config or {}
    name = provider_name or settings.image_provider
    return get_visual_provider(name, cfg)


def get_video_provider(provider_name: str | None = None, config: dict | None = None) -> VisualAssetProvider:
    cfg = config or {}
    name = provider_name or settings.video_provider
    return get_visual_provider(name, cfg)
