from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.research.scheduler import ResearchSchedulerService, serialize_run, serialize_schedule

router = APIRouter(prefix="/api/v1/research-scheduler", tags=["research-scheduler"])


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=2, max_length=500)
    cadence_hours: float = Field(default=24, ge=1, le=168)
    next_run_at: datetime | None = None
    provider: str | None = Field(default=None, max_length=80)
    max_results: int = Field(default=10, ge=3, le=50)
    published_after_days: int | None = Field(default=30, ge=1, le=3650)
    auto_generate_ideas: bool = False
    idea_count: int = Field(default=5, ge=1, le=50)
    goal: str = Field(default="balanced", pattern="^(growth|authority|monetization|balanced)$")
    catch_up: bool = False
    max_runs_per_day: int = Field(default=3, ge=1, le=24)


@router.post("/channels/{channel_id}/schedules")
async def create_schedule(channel_id: str, payload: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    try:
        row = await ResearchSchedulerService(db).create_schedule(channel_id=channel_id, **payload.model_dump())
        return serialize_schedule(row)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/channels/{channel_id}/schedules")
async def list_schedules(channel_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    try:
        rows = await ResearchSchedulerService(db).list_schedules(channel_id, limit)
        return {"channel_id": channel_id, "schedules": [serialize_schedule(x) for x in rows]}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    try:
        row = await ResearchSchedulerService(db)._get(schedule_id)
        return serialize_schedule(row)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/schedules/{schedule_id}/run", status_code=202)
async def run_now(schedule_id: str, db: AsyncSession = Depends(get_db)):
    try:
        row = await ResearchSchedulerService(db).run_now(schedule_id)
        return {"schedule": serialize_schedule(row), "queued": True}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/schedules/{schedule_id}/enable")
async def enable(schedule_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return serialize_schedule(await ResearchSchedulerService(db).enable(schedule_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/schedules/{schedule_id}/disable")
async def disable(schedule_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return serialize_schedule(await ResearchSchedulerService(db).disable(schedule_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/schedules/{schedule_id}/runs")
async def runs(schedule_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    try:
        rows = await ResearchSchedulerService(db).list_runs(schedule_id, limit)
        return {"schedule_id": schedule_id, "runs": [serialize_run(x) for x in rows]}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
