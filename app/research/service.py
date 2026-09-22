from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Channel, ResearchReport
from app.research import get_research_provider


class ResearchService:
    def __init__(self):
        self.provider = get_research_provider()

    async def run(self, db: AsyncSession, *, channel_id: str, query: str, video_project_id: str | None = None, max_results: int = 10) -> ResearchReport:
        channel = await db.get(Channel, uuid.UUID(channel_id))
        if not channel:
            raise ValueError("Channel not found")
        result = await self.provider.search(query=query, max_results=max_results)
        results = result.get("results", [])
        competitor_findings = []
        for item in results:
            if isinstance(item, dict):
                title = item.get("title", "")
                competitor_findings.append({
                    "title": title,
                    "url": item.get("url") or item.get("link"),
                    "snippet": item.get("snippet") or item.get("content", ""),
                    "type": "discovery",
                })
        gaps = []
        if not results:
            gaps.append("No external results were returned; treat research as incomplete.")
        else:
            gaps.append("Cluster discovered sources by angle, format, and recurring audience questions before scripting.")
        report = ResearchReport(
            channel_id=channel.id,
            video_project_id=uuid.UUID(video_project_id) if video_project_id else None,
            query=query,
            sources=results,
            competitor_findings=competitor_findings,
            audience_findings=[],
            content_gaps=gaps,
            summary=f"Research completed using {self.provider.name} with {len(results)} result(s).",
            provider=self.provider.name,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        return report
