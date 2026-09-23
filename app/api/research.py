from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from app.auth.security import Principal, permission_dependency
from app.db.session import get_db
from app.models import Channel
from app.research.service import ResearchService
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/research", tags=["research"])


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    video_project_id: str | None = None
    max_results: int = Field(default=10, ge=1, le=30)


@router.post("/channels/{channel_id}")
async def run_research(
    channel_id: str,
    payload: ResearchRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("research:write")),
):
    try:
        channel_uuid = UUID(channel_id)
    except ValueError as exc:
        raise HTTPException(404, "Channel not found") from exc
    channel = await db.get(Channel, channel_uuid)
    if not channel or channel.owner_id != principal.scope_key:
        raise HTTPException(404, "Channel not found")
    try:
        report = await ResearchService().run(
            db,
            channel_id=channel_id,
            query=payload.query,
            video_project_id=payload.video_project_id,
            max_results=payload.max_results,
        )
        return {
            "id": str(report.id),
            "channel_id": channel_id,
            "video_project_id": str(report.video_project_id) if report.video_project_id else None,
            "query": report.query,
            "provider": report.provider,
            "summary": report.summary,
            "sources": report.sources,
            "competitor_findings": report.competitor_findings,
            "audience_findings": report.audience_findings,
            "content_gaps": report.content_gaps,
        }
    except ValueError as exc:
        raise HTTPException(404, str(exc))
