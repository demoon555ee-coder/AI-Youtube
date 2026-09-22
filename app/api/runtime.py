from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.models import AgentDefinition, AgentHandoff, AgentTask, Channel
from app.runtime.service import AgentRuntimeError, AgentRuntimeService

router = APIRouter(prefix="/api/v1/agents", tags=["agent-runtime"])


class TaskCreate(BaseModel):
    agent_key: str = Field(min_length=1, max_length=80)
    task_type: str = Field(min_length=1, max_length=80)
    action_type: str = Field(min_length=1, max_length=80)
    input_data: dict = Field(default_factory=dict)
    budget_usd: float = Field(default=0, ge=0)
    priority: int = Field(default=50, ge=0, le=100)
    parent_task_id: UUID | None = None
    dependencies: list[UUID] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=255)
    confidence: float = Field(default=0.75, ge=0, le=1)
    requested_mode: str = Field(default="auto", pattern="^(auto|approve|defer|block)$")
    plan_node_id: UUID | None = None
    workflow_run_id: UUID | None = None
    project_id: UUID | None = None


class HandoffRequest(BaseModel):
    to_agent: str = Field(min_length=1, max_length=80)
    lease_token: str = Field(min_length=16, max_length=255)
    payload: dict = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2000)


class DelegateRequest(BaseModel):
    to_agent: str = Field(min_length=1, max_length=80)
    lease_token: str = Field(min_length=16, max_length=255)
    task_type: str = Field(min_length=1, max_length=80)
    action_type: str = Field(min_length=1, max_length=80)
    input_data: dict = Field(default_factory=dict)
    budget_usd: float = Field(default=0, ge=0)
    priority: int = Field(default=50, ge=0, le=100)


class CompleteRequest(BaseModel):
    lease_token: str = Field(min_length=16, max_length=255)
    output: dict = Field(default_factory=dict)
    actual_cost_usd: float = Field(default=0, ge=0)


class FailRequest(BaseModel):
    lease_token: str = Field(min_length=16, max_length=255)
    error: str = Field(min_length=1, max_length=4000)


def _access(channel, principal):
    if principal.is_dev_fallback:
        return
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return
    if channel.owner_id == principal.scope_key:
        return
    raise HTTPException(404, "Resource not found")


async def _channel(channel_id, db, principal):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _access(channel, principal)
    return channel


def _task(t):
    return {
        "id": str(t.id),
        "channel_id": str(t.channel_id),
        "project_id": str(t.project_id) if t.project_id else None,
        "plan_node_id": str(t.plan_node_id) if t.plan_node_id else None,
        "workflow_run_id": str(t.workflow_run_id) if t.workflow_run_id else None,
        "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
        "agent_key": t.agent_key,
        "task_type": t.task_type,
        "action_type": t.action_type,
        "risk_tier": t.risk_tier,
        "governance_mode": t.governance_mode,
        "governance_approved": t.governance_approved,
        "governance_policy_version": t.governance_policy_version,
        "confidence": t.confidence,
        "status": t.status,
        "priority": t.priority,
        "requested_budget_usd": t.requested_budget_usd,
        "reserved_budget_usd": t.reserved_budget_usd,
        "actual_cost_usd": t.actual_cost_usd,
        "input_data": t.input_data or {},
        "output_data": t.output_data or {},
        "error_message": t.error_message,
        "created_at": t.created_at,
        "started_at": t.started_at,
        "completed_at": t.completed_at,
    }


@router.get("/channels/{channel_id}/agents")
async def agents(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _channel(channel_id, db, principal)
    service = AgentRuntimeService(db)
    await service.ensure_agents(channel.id)
    await db.commit()
    rows = (await db.execute(select(AgentDefinition).where(AgentDefinition.channel_id == channel.id).order_by(AgentDefinition.agent_key))).scalars().all()
    return {"channel_id": str(channel.id), "agents": [{
        "id": str(a.id), "agent_key": a.agent_key, "display_name": a.display_name,
        "capabilities": a.capabilities or [], "enabled": a.enabled,
        "max_concurrency": a.max_concurrency, "default_budget_usd": a.default_budget_usd,
    } for a in rows]}


@router.post("/channels/{channel_id}/tasks")
async def create_task(channel_id: UUID, payload: TaskCreate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    channel = await _channel(channel_id, db, principal)
    try:
        task = await AgentRuntimeService(db).create_task(
            channel_id=channel.id,
            **{**payload.model_dump(), "budget_usd": Decimal(str(payload.budget_usd))},
        )
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return _task(task)


@router.get("/channels/{channel_id}/tasks")
async def list_tasks(channel_id: UUID, status: str | None = None, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _channel(channel_id, db, principal)
    stmt = select(AgentTask).where(AgentTask.channel_id == channel.id).order_by(AgentTask.priority.desc(), AgentTask.created_at.asc()).limit(200)
    if status:
        stmt = stmt.where(AgentTask.status == status.upper())
    rows = (await db.execute(stmt)).scalars().all()
    return {"tasks": [_task(r) for r in rows]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    readiness = await AgentRuntimeService(db).readiness(task)
    return {"task": _task(task), "readiness": readiness}


@router.post("/tasks/{task_id}/lease")
async def lease_task(task_id: UUID, ttl_seconds: int = 300, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    try:
        lease = await AgentRuntimeService(db).acquire_lease(task_id=task.id, agent_key=task.agent_key, ttl_seconds=ttl_seconds)
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return {"task": _task(task), "lease": {"id": str(lease.id), "token": lease.lease_token, "expires_at": lease.expires_at}}


@router.post("/tasks/{task_id}/heartbeat")
async def heartbeat(task_id: UUID, token: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    try:
        lease = await AgentRuntimeService(db).heartbeat(task_id=task.id, lease_token=token)
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return {"expires_at": lease.expires_at}


@router.post("/tasks/{task_id}/complete")
async def complete(task_id: UUID, payload: CompleteRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    try:
        task = await AgentRuntimeService(db).complete(task_id=task.id, lease_token=payload.lease_token, output_data=payload.output, actual_cost_usd=Decimal(str(payload.actual_cost_usd)))
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return _task(task)


@router.post("/tasks/{task_id}/fail")
async def fail(task_id: UUID, payload: FailRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    try:
        task = await AgentRuntimeService(db).fail(task_id=task.id, lease_token=payload.lease_token, error=payload.error)
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return _task(task)


@router.post("/tasks/{task_id}/delegate")
async def delegate(task_id: UUID, payload: DelegateRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    try:
        child = await AgentRuntimeService(db).delegate(task=task, target_agent_key=payload.to_agent, lease_token=payload.lease_token, task_type=payload.task_type, action_type=payload.action_type, input_data=payload.input_data, budget_usd=Decimal(str(payload.budget_usd)), priority=payload.priority)
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return _task(child)


@router.post("/tasks/{task_id}/handoff")
async def handoff(task_id: UUID, payload: HandoffRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    try:
        row = await AgentRuntimeService(db).handoff(task=task, target_agent_key=payload.to_agent, lease_token=payload.lease_token, reason=payload.reason, payload=payload.payload)
    except AgentRuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    return {"id": str(row.id), "task_id": str(row.task_id), "from_agent": row.from_agent, "to_agent": row.to_agent, "handoff_type": row.handoff_type, "payload": row.payload, "reason": row.reason}


@router.get("/tasks/{task_id}/handoffs")
async def handoffs(task_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    await _channel(task.channel_id, db, principal)
    rows = (await db.execute(select(AgentHandoff).where(AgentHandoff.task_id == task.id).order_by(AgentHandoff.created_at))).scalars().all()
    return {"handoffs": [{"id": str(r.id), "from_agent": r.from_agent, "to_agent": r.to_agent, "type": r.handoff_type, "payload": r.payload or {}, "reason": r.reason, "created_at": r.created_at} for r in rows]}
