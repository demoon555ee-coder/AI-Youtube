from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, require_roles
from app.db.session import get_db
from app.learning.service import AgentLearningService
from app.models import AgentLearningObservation, AgentStrategyProposal, AgentStrategyVersion, Channel

router = APIRouter(prefix="/api/v1/learning", tags=["agent-learning"])


class ProposalCreate(BaseModel):
    agent_key: str = Field(min_length=1, max_length=80)
    action_type: str = Field(min_length=1, max_length=80)
    observation_limit: int = Field(default=25, ge=5, le=100)
    objective: str = Field(default="improve successful outcome rate without changing governance", max_length=1000)


class DecisionRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)


async def _channel(channel_id, db, principal):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    if principal.is_dev_fallback:
        return channel
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return channel
    if channel.owner_id == principal.scope_key:
        return channel
    raise HTTPException(404, "Resource not found")


@router.get("/channels/{channel_id}/observations")
async def observations(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    await _channel(channel_id, db, principal)
    rows = (
        await db.execute(
            select(AgentLearningObservation)
            .where(AgentLearningObservation.channel_id == channel_id)
            .order_by(AgentLearningObservation.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return {"observations": [AgentLearningService.observation_json(r) for r in rows]}


@router.post("/channels/{channel_id}/proposals")
async def propose(channel_id: UUID, payload: ProposalCreate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    channel = await _channel(channel_id, db, principal)
    try:
        row = await AgentLearningService(db).propose_recent(
            channel=channel,
            agent_key=payload.agent_key,
            action_type=payload.action_type,
            limit=payload.observation_limit,
            objective=payload.objective,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return AgentLearningService.proposal_json(row)


@router.get("/channels/{channel_id}/proposals")
async def proposals(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    await _channel(channel_id, db, principal)
    rows = (
        await db.execute(
            select(AgentStrategyProposal)
            .where(AgentStrategyProposal.channel_id == channel_id)
            .order_by(AgentStrategyProposal.created_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return {"proposals": [AgentLearningService.proposal_json(r) for r in rows]}


@router.post("/proposals/{proposal_id}/approve")
async def approve(proposal_id: UUID, payload: DecisionRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    row = await db.get(AgentStrategyProposal, proposal_id)
    if not row:
        raise HTTPException(404, "Proposal not found")
    await _channel(row.channel_id, db, principal)
    try:
        row = await AgentLearningService(db).approve_proposal(proposal=row, principal=principal, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return AgentLearningService.proposal_json(row)


@router.post("/proposals/{proposal_id}/reject")
async def reject(proposal_id: UUID, payload: DecisionRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    row = await db.get(AgentStrategyProposal, proposal_id)
    if not row:
        raise HTTPException(404, "Proposal not found")
    await _channel(row.channel_id, db, principal)
    try:
        row = await AgentLearningService(db).reject_proposal(proposal=row, principal=principal, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return AgentLearningService.proposal_json(row)


@router.post("/proposals/{proposal_id}/activate")
async def activate(proposal_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    row = await db.get(AgentStrategyProposal, proposal_id)
    if not row:
        raise HTTPException(404, "Proposal not found")
    await _channel(row.channel_id, db, principal)
    try:
        version = await AgentLearningService(db).activate(proposal=row, principal=principal)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"id": str(version.id), "agent_key": version.agent_key, "version": version.version, "active": version.active, "strategy": version.strategy}


@router.get("/channels/{channel_id}/strategies")
async def strategies(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    await _channel(channel_id, db, principal)
    rows = (
        await db.execute(
            select(AgentStrategyVersion)
            .where(AgentStrategyVersion.channel_id == channel_id, AgentStrategyVersion.active.is_(True))
            .order_by(AgentStrategyVersion.agent_key)
        )
    ).scalars().all()
    return {"strategies": [{"id": str(r.id), "agent_key": r.agent_key, "version": r.version, "active": r.active, "strategy": r.strategy or {}, "activated_at": r.activated_at} for r in rows]}
