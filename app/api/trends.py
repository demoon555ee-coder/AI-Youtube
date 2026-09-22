from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.research.graph_service import ResearchGraphService
from app.trends.diff import TrendDiffService, serialize_snapshot, serialize_trend_event

router = APIRouter(prefix="/api/v1/trends", tags=["trends"])


class TrendScanRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=10, ge=3, le=50)
    published_after_days: int | None = Field(default=30, ge=1, le=3650)
    provider: str | None = Field(default=None, max_length=80)


@router.post("/channels/{channel_id}/scan")
async def scan_with_trend_diff(channel_id: str, payload: TrendScanRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await ResearchGraphService(provider_name=payload.provider).scan(
            db,
            channel_id=channel_id,
            query=payload.query,
            max_results=payload.max_results,
            published_after_days=payload.published_after_days,
        )
        return result
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/channels/{channel_id}/events")
async def list_events(
    channel_id: str,
    query: str | None = None,
    event_type: str | None = Query(default=None, pattern="^(NEW|RISING|FALLING|DISAPPEARING)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = await TrendDiffService(db).list_events(channel_id, query=query, event_type=event_type, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"channel_id": channel_id, "events": [serialize_trend_event(x) for x in rows]}


@router.get("/channels/{channel_id}/snapshots")
async def list_snapshots(channel_id: str, query: str | None = None, limit: int = Query(default=30, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    try:
        rows = await TrendDiffService(db).list_snapshots(channel_id, query=query, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"channel_id": channel_id, "snapshots": [serialize_snapshot(x) for x in rows]}
