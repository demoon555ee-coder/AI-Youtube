from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.research.graph_service import ResearchGraphService, graph_snapshot, list_opportunities, serialize_opportunity

router = APIRouter(prefix="/api/v1/research-intelligence", tags=["research-intelligence"])


class ScanRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=10, ge=3, le=50)
    published_after_days: int | None = Field(default=30, ge=1, le=365)
    provider: str | None = Field(default=None, max_length=80)


@router.post("/channels/{channel_id}/scan")
async def scan(channel_id: str, payload: ScanRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await ResearchGraphService(provider_name=payload.provider).scan(
            db, channel_id=channel_id, query=payload.query,
            max_results=payload.max_results, published_after_days=payload.published_after_days,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/channels/{channel_id}/opportunities")
async def opportunities(channel_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    try:
        rows = await list_opportunities(db, channel_id, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"channel_id": channel_id, "opportunities": [serialize_opportunity(x) for x in rows]}


@router.get("/channels/{channel_id}/graph")
async def graph(channel_id: str, limit: int = 150, db: AsyncSession = Depends(get_db)):
    try:
        return await graph_snapshot(db, channel_id, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

from pydantic import Field
from app.content.researched import generate_from_opportunities

class GenerateIdeasRequest(BaseModel):
    opportunity_ids: list[str] = Field(min_length=1, max_length=20)
    count: int = Field(default=10, ge=1, le=50)
    goal: str = Field(default="balanced", pattern="^(growth|authority|monetization|balanced)$")


@router.post("/channels/{channel_id}/opportunities/generate-ideas")
async def generate_ideas_from_opportunities(channel_id: str, payload: GenerateIdeasRequest, db: AsyncSession = Depends(get_db)):
    try:
        rows = await generate_from_opportunities(
            db, channel_id=channel_id, opportunity_ids=payload.opportunity_ids,
            count=payload.count, goal=payload.goal,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "channel_id": channel_id,
        "ideas": [{
            "id": str(x.id), "topic": x.topic, "title": x.title, "hook": x.hook,
            "angle": x.angle, "composite_score": x.composite_score,
            "research_opportunity_id": str(x.research_opportunity_id) if x.research_opportunity_id else None,
        } for x in rows]
    }
