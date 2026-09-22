from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.auth.security import Principal, get_current_principal
from app.models import Channel, ContentPlan, ContentPlanItem

router = APIRouter(prefix="/api/v1/portfolio/autopilot", tags=["portfolio-autopilot"])


@router.get("/queue")
async def queue(limit: int = 50, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    rows = await db.execute(
        select(ContentPlanItem, ContentPlan, Channel)
        .join(ContentPlan, ContentPlan.id == ContentPlanItem.plan_id)
        .join(Channel, Channel.id == ContentPlan.channel_id)
        .where(Channel.owner_id == principal.scope_key, ContentPlan.status == "ACTIVE", ContentPlanItem.status.in_({"PLANNED", "MATERIALIZED", "ENQUEUING", "QUEUED"}))
        .order_by(ContentPlanItem.production_start_at.asc())
        .limit(limit)
    )
    now = datetime.utcnow()
    return {"items": [{
        "id": str(item.id), "channel_id": str(channel.id), "channel_name": channel.name,
        "plan_id": str(plan.id), "position": item.position, "title": item.title,
        "status": item.status, "production_start_at": item.production_start_at.isoformat(),
        "scheduled_for": item.scheduled_for.isoformat(), "due": item.production_start_at <= now,
        "project_id": str(item.project_id) if item.project_id else None,
        "auto_publish": plan.auto_publish,
    } for item, plan, channel in rows.all()]}
