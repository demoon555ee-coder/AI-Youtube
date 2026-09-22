from __future__ import annotations
from typing import Any
from app.research.base import ResearchProvider


class MockResearchProvider(ResearchProvider):
    name = "mock_research"

    async def search(self, *, query: str, max_results: int = 10) -> dict[str, Any]:
        return {
            "query": query,
            "provider": self.name,
            "results": [
                {
                    "title": f"Research result for: {query}",
                    "url": "https://example.com/research",
                    "snippet": "Deterministic local research placeholder for development and CI.",
                }
            ][:max_results],
        }
