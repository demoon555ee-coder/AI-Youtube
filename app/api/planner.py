from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.models import Channel, AgentPlan
from app.planner.service import AgentPlannerService

router = APIRouter(prefix="/api/v1/planner", tags=["agent-planner"])

class PlanCreate(BaseModel):
    goal: str = Field(min_length=3, max_length=4000)
    context: dict = {}
    budget_usd: float = Field(default=0, ge=0)
    project_id: UUID | None = None
    blueprint: list[dict] | None = None

class ReplanRequest(BaseModel):
    failed_node_key: str
    reason: str = Field(min_length=1, max_length=2000)
    preferred_agent: str | None = None

async def _channel(channel_id, db, principal):
    channel = await db.get(Channel, channel_id)
    if not channel: raise HTTPException(404, "Channel not found")
    if not principal.is_dev_fallback and principal.organization_id is not None and channel.organization_id != principal.organization_id and channel.owner_id != principal.scope_key:
        raise HTTPException(404, "Resource not found")
    return channel

@router.post("/channels/{channel_id}/plans")
async def create_plan(channel_id: UUID, payload: PlanCreate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    channel = await _channel(channel_id, db, principal)
    try:
        plan = await AgentPlannerService(db).create_plan(channel=channel, goal=payload.goal, context=payload.context, budget_usd=payload.budget_usd, project_id=payload.project_id, blueprint=payload.blueprint)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return AgentPlannerService._plan_json(plan)

@router.get("/plans/{plan_id}")
async def get_plan(plan_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    plan = await db.get(AgentPlan, plan_id)
    if not plan: raise HTTPException(404, "Plan not found")
    await _channel(plan.channel_id, db, principal)
    return await AgentPlannerService(db).get_graph(plan)

@router.get("/plans/{plan_id}/ready")
async def ready_nodes(plan_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    plan = await db.get(AgentPlan, plan_id)
    if not plan: raise HTTPException(404, "Plan not found")
    await _channel(plan.channel_id, db, principal)
    nodes = await AgentPlannerService(db).readiness(plan)
    return {"plan_id": str(plan.id), "ready": [AgentPlannerService._node_json(n) for n in nodes]}

@router.post("/plans/{plan_id}/materialize")
async def materialize(plan_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    plan = await db.get(AgentPlan, plan_id)
    if not plan: raise HTTPException(404, "Plan not found")
    await _channel(plan.channel_id, db, principal)
    nodes = await AgentPlannerService(db).materialize_ready(plan)
    await db.commit()
    return {"plan_id": str(plan.id), "status": plan.status, "materialized": [AgentPlannerService._node_json(n) for n in nodes]}

@router.post("/plans/{plan_id}/replan")
async def replan(plan_id: UUID, payload: ReplanRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    plan = await db.get(AgentPlan, plan_id)
    if not plan: raise HTTPException(404, "Plan not found")
    await _channel(plan.channel_id, db, principal)
    try:
        plan = await AgentPlannerService(db).replan(plan, failed_node_key=payload.failed_node_key, reason=payload.reason, preferred_agent=payload.preferred_agent)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return AgentPlannerService._plan_json(plan)
