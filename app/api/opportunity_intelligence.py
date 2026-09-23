from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.security import Principal, permission_dependency
from app.models import Channel
from app.models import OpportunityDecision, ResearchOpportunity
from app.opportunity_intelligence.service import OpportunityIntelligenceService, serialize_decision, serialize_run

router = APIRouter(prefix="/api/v1/opportunity-intelligence", tags=["opportunity-intelligence"])


async def _ensure_owned_channel(channel_id: str, db: AsyncSession, principal: Principal) -> None:
    try:
        channel = await db.get(Channel, channel_id)
    except Exception as exc:
        raise HTTPException(404, "Channel not found") from exc
    if not channel or channel.owner_id != principal.scope_key:
        raise HTTPException(404, "Channel not found")


class AnalyzeRequest(BaseModel):
    goal: str = Field(default="balanced", pattern="^(growth|authority|monetization|balanced)$")
    limit: int = Field(default=50, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


@router.post("/channels/{channel_id}/analyze")
async def analyze(channel_id: str, payload: AnalyzeRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("content:write"))):
    await _ensure_owned_channel(channel_id, db, principal)
    try:
        run = await OpportunityIntelligenceService(db).analyze(
            channel_id=channel_id, goal=payload.goal, limit=payload.limit, min_score=payload.min_score
        )
        return serialize_run(run)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/channels/{channel_id}/decisions")
async def decisions(channel_id: str, limit: int = Query(default=50, ge=1, le=100), db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("read"))):
    await _ensure_owned_channel(channel_id, db, principal)
    try:
        rows = await OpportunityIntelligenceService(db).latest_decisions(channel_id=channel_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    opportunity_ids = [x.opportunity_id for x in rows]
    q = await db.execute(select(ResearchOpportunity).where(ResearchOpportunity.id.in_(opportunity_ids))) if opportunity_ids else None
    by_id = {x.id: x for x in q.scalars().all()} if q else {}
    return {"channel_id": channel_id, "decisions": [serialize_decision(row, by_id.get(row.opportunity_id)) for row in rows]}


@router.get("/channels/{channel_id}/runs")
async def runs(channel_id: str, limit: int = Query(default=20, ge=1, le=100), db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("read"))):
    await _ensure_owned_channel(channel_id, db, principal)
    try:
        rows = await OpportunityIntelligenceService(db).list_runs(channel_id=channel_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"channel_id": channel_id, "runs": [serialize_run(x) for x in rows]}
