from __future__ import annotations

from typing import Any
import httpx
from app.research.base import ResearchProvider
from app.config import settings
from app.resilience.http import request_with_retry


class HTTPJSONResearchProvider(ResearchProvider):
    """Vendor-neutral search adapter.

    The configured endpoint receives {query, max_results}; the response must contain
    a `results` array or a `data.results` array. This keeps research provider logic
    swappable for Tavily-like, SerpAPI proxy, or internal search services.
    """

    name = "http_json_research"

    def __init__(self, *, endpoint: str, api_key: str = "", timeout_seconds: float = 30.0):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def search(self, *, query: str, max_results: int = 10) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await request_with_retry(
                lambda: client.post(
                    self.endpoint,
                    json={"query": query, "max_results": max_results},
                    headers=headers,
                ),
                max_retries=settings.llm_max_retries,
            )
            response.raise_for_status()
            payload = response.json()
        results = payload.get("results") or payload.get("data", {}).get("results") or []
        if not isinstance(results, list):
            raise ValueError("Research provider returned an invalid results payload")
        return {"query": query, "provider": self.name, "results": results[:max_results], "raw": payload}
