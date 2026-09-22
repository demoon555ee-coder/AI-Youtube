from __future__ import annotations
import os
from app.config import settings
from app.research.base import ResearchProvider
from app.research.mock import MockResearchProvider
from app.research.http_json import HTTPJSONResearchProvider
from app.research.youtube_data import YouTubeDataResearchProvider


def get_research_provider(provider_name: str | None = None, config: dict | None = None) -> ResearchProvider:
    name = provider_name or settings.research_provider
    cfg = config or {}
    if name == "mock" or cfg.get("kind") == "mock":
        return MockResearchProvider()
    if name in {"youtube_data", "youtube_data_api"} or cfg.get("kind") in {"youtube_data", "youtube_data_api"}:
        api_key = str((os.getenv(str(cfg["api_key_env"])) if cfg.get("api_key_env") else settings.youtube_research_api_key) or "")
        return YouTubeDataResearchProvider(
            api_key=api_key,
            region_code=str(cfg.get("region_code") or settings.youtube_research_region_code),
            language=str(cfg.get("language") or settings.youtube_research_language),
            order=str(cfg.get("order") or settings.youtube_research_order),
            timeout_seconds=settings.research_timeout_seconds,
        )
    if name == "http_json" or cfg.get("kind") == "http_json":
        endpoint = str(cfg.get("endpoint") or settings.research_endpoint)
        api_key = str((os.getenv(str(cfg["api_key_env"])) if cfg.get("api_key_env") else settings.research_api_key) or "")
        if not endpoint:
            raise RuntimeError("HTTP JSON research provider requires endpoint")
        return HTTPJSONResearchProvider(endpoint=endpoint, api_key=api_key, timeout_seconds=settings.research_timeout_seconds)
    raise ValueError(f"Unknown research provider: {name}")
