from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
import httpx
from app.research.base import ResearchProvider


class YouTubeDataResearchProvider(ResearchProvider):
    """Public-data research adapter using YouTube Data API v3.

    Uses API-key access for public search/statistics and keeps calls deliberately
    small: one search.list request plus one videos.list enrichment request.
    """
    name = "youtube_data_api"

    def __init__(self, *, api_key: str, region_code: str = "US", language: str = "en", order: str = "viewCount", timeout_seconds: float = 30.0):
        self.api_key = api_key
        self.region_code = region_code
        self.language = language
        self.order = order if order in {"viewCount", "date", "rating", "relevance"} else "viewCount"
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://www.googleapis.com/youtube/v3"

    async def search(self, *, query: str, max_results: int = 10, published_after_days: int | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("YouTube research requires YOUTUBE_RESEARCH_API_KEY")
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": min(max(1, max_results), 50),
            "order": self.order,
            "regionCode": self.region_code,
            "relevanceLanguage": self.language,
            "key": self.api_key,
        }
        if published_after_days and published_after_days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=published_after_days)
            params["publishedAfter"] = cutoff.isoformat().replace("+00:00", "Z")

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.base_url}/search", params=params)
            response.raise_for_status()
            search_payload = response.json()
            items = search_payload.get("items") or []
            video_ids = [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]
            stats = {}
            if video_ids:
                enrich_params = {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(video_ids[:50]),
                    "key": self.api_key,
                }
                enrich_response = await client.get(f"{self.base_url}/videos", params=enrich_params)
                enrich_response.raise_for_status()
                enrich_payload = enrich_response.json()
                stats = {item.get("id"): item for item in (enrich_payload.get("items") or [])}

        results = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet") or {}
            enriched = stats.get(video_id, {})
            statistics = enriched.get("statistics") or {}
            content_details = enriched.get("contentDetails") or {}
            results.append({
                "id": video_id,
                "type": "video",
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt"),
                "thumbnail_url": ((snippet.get("thumbnails") or {}).get("high") or {}).get("url"),
                "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                "views": int(statistics.get("viewCount") or 0),
                "likes": int(statistics.get("likeCount") or 0),
                "comments": int(statistics.get("commentCount") or 0),
                "duration": content_details.get("duration"),
            })
        return {
            "query": query,
            "provider": self.name,
            "results": results[:max_results],
            "metadata": {
                "order": self.order,
                "region_code": self.region_code,
                "published_after_days": published_after_days,
            },
        }
