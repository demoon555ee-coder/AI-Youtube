import uuid
from app.config import settings
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.auth.security import Principal, get_current_principal, require_roles
from app.autopilot.service import AutopilotService
from app.schemas.autopilot import AutopilotPlanCreateRequest, MaterializeRequest

router = APIRouter(prefix="/api/v1/autopilot", tags=["autopilot"])


async def _access(channel_id, db, principal):
    from app.models.channel import Channel
    channel = await db.get(Channel, uuid.UUID(channel_id))
    if not channel:
        raise HTTPException(404, "Channel not found")
    if principal.is_dev_fallback:
        return channel
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return channel
    if channel.owner_id == principal.scope_key:
        return channel
    raise HTTPException(404, "Resource not found")


def _plan_json(plan):
    return {
        "id": str(plan.id), "channel_id": str(plan.channel_id), "name": plan.name,
        "start_date": plan.start_date.isoformat(), "end_date": plan.end_date.isoformat(),
        "timezone": plan.timezone, "goal": plan.goal, "cadence_per_week": plan.cadence_per_week,
        "publish_time": plan.publish_time, "weekdays": plan.weekdays or [],
        "production_lead_hours": plan.production_lead_hours, "auto_publish": plan.auto_publish,
        "status": plan.status, "settings": plan.settings or [],
    }


def _item_json(item):
    return {
        "id": str(item.id), "position": item.position, "idea_id": str(item.idea_id) if item.idea_id else None,
        "project_id": str(item.project_id) if item.project_id else None,
        "topic": item.topic, "title": item.title, "hook": item.hook, "angle": item.angle,
        "format": item.format, "scheduled_for": item.scheduled_for.isoformat(),
        "production_start_at": item.production_start_at.isoformat(), "status": item.status,
        "metadata": item.metadata_json or {}, "error_message": item.error_message,
    }


@router.post("/channels/{channel_id}/plans")
async def create_plan(channel_id: str, payload: AutopilotPlanCreateRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    await _access(channel_id, db, principal)
    try:
        plan = await AutopilotService(db).generate_plan(
            channel_id=channel_id, name=payload.name, start_date=payload.start_date,
            horizon_days=payload.horizon_days, cadence_per_week=payload.cadence_per_week,
            publish_time=payload.publish_time, weekdays=payload.weekdays,
            goal=payload.goal, timezone_name=payload.timezone,
            production_lead_hours=payload.production_lead_hours,
            auto_publish=payload.auto_publish, seed_topics=payload.seed_topics,
        )
        return _plan_json(plan)
    except Exception as exc:
        raise HTTPException(status_code=500 if settings.app_env == "production" else 400, detail="Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.get("/channels/{channel_id}/plans")
async def list_plans(channel_id: str, limit: int = 20, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    await _access(channel_id, db, principal)
    try:
        plans = await AutopilotService(db).list_plans(channel_id, min(max(limit, 1), 100))
        return {"channel_id": channel_id, "plans": [_plan_json(plan) for plan in plans]}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/channels/{channel_id}/plans/{plan_id}")
async def get_plan(channel_id: str, plan_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    await _access(channel_id, db, principal)
    try:
        plan, items = await AutopilotService(db).get_plan(channel_id, plan_id)
        return {"plan": _plan_json(plan), "items": [_item_json(item) for item in items]}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/channels/{channel_id}/plans/{plan_id}/activate")
async def activate_plan(channel_id: str, plan_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    await _access(channel_id, db, principal)
    try:
        plan = await AutopilotService(db).activate(channel_id, plan_id)
        return _plan_json(plan)
    except Exception as exc:
        raise HTTPException(status_code=500 if settings.app_env == "production" else 400, detail="Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/channels/{channel_id}/plans/{plan_id}/pause")
async def pause_plan(channel_id: str, plan_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    await _access(channel_id, db, principal)
    try:
        plan = await AutopilotService(db).pause(channel_id, plan_id)
        return _plan_json(plan)
    except Exception as exc:
        raise HTTPException(status_code=500 if settings.app_env == "production" else 400, detail="Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/channels/{channel_id}/plans/{plan_id}/materialize")
async def materialize_plan(channel_id: str, plan_id: str, payload: MaterializeRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    await _access(channel_id, db, principal)
    try:
        items = await AutopilotService(db).materialize_items(channel_id, plan_id, payload.item_ids)
        return {"plan_id": plan_id, "materialized": len(items), "items": [_item_json(item) for item in items]}
    except Exception as exc:
        raise HTTPException(status_code=500 if settings.app_env == "production" else 400, detail="Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.get("/channels/{channel_id}/plans/{plan_id}/summary")
async def plan_summary(channel_id: str, plan_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    await _access(channel_id, db, principal)
    try:
        return await AutopilotService(db).summary(channel_id, plan_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
