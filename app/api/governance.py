from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, permission_dependency, require_roles
from app.db.session import get_db
from app.models import Channel, AgentGovernancePolicy, AgentActionPolicy, AgentApprovalRequest, AgentGovernanceEvent, AutonomousExecutionRun
from app.governance.service import AgentGovernanceService

router = APIRouter(prefix="/api/v1/governance", tags=["agent-governance"])


class PolicyUpdateRequest(BaseModel):
    enabled: bool | None = None
    emergency_kill_switch: bool | None = None
    default_mode: str | None = Field(default=None, pattern="^(auto|approve|defer|block)$")
    approval_timeout_minutes: int | None = Field(default=None, ge=1, le=10080)
    automation_policies: dict | None = None


class ActionPolicyUpdateRequest(BaseModel):
    automation_mode: str | None = Field(default=None, pattern="^(auto|approve|defer|block)$")
    risk_tier: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    enabled: bool | None = None
    require_human_approval: bool | None = None
    max_cost_usd: float | None = Field(default=None, ge=0)
    min_confidence: float | None = Field(default=None, ge=0, le=1)


class ApprovalDecisionRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)


def _access(channel, principal):
    if principal.is_dev_fallback:
        return
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return
    if channel.owner_id == principal.scope_key:
        return
    raise HTTPException(404, "Resource not found")


def _policy_json(policy, actions):
    return {
        "id": str(policy.id),
        "channel_id": str(policy.channel_id),
        "enabled": policy.enabled,
        "emergency_kill_switch": policy.emergency_kill_switch,
        "default_mode": policy.default_mode,
        "approval_timeout_minutes": policy.approval_timeout_minutes,
        "policy_version": policy.policy_version,
        "automation_policies": policy.automation_policies or {},
        "actions": [
            {
                "id": str(a.id), "action_type": a.action_type, "risk_tier": a.risk_tier,
                "automation_mode": a.automation_mode, "enabled": a.enabled,
                "require_human_approval": a.require_human_approval,
                "max_cost_usd": a.max_cost_usd, "min_confidence": a.min_confidence,
                "settings": a.settings or {},
            } for a in actions
        ],
    }


async def _channel(channel_id, db, principal):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _access(channel, principal)
    return channel


@router.get("/channels/{channel_id}/policy")
async def get_policy(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _channel(channel_id, db, principal)
    service = AgentGovernanceService(db)
    policy = await service.ensure_policy(channel)
    actions = (await db.execute(select(AgentActionPolicy).where(AgentActionPolicy.governance_policy_id == policy.id).order_by(AgentActionPolicy.action_type))).scalars().all()
    await db.commit()
    return _policy_json(policy, actions)


@router.patch("/channels/{channel_id}/policy")
async def update_policy(channel_id: UUID, payload: PolicyUpdateRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    channel = await _channel(channel_id, db, principal)
    policy = await AgentGovernanceService(db).ensure_policy(channel)
    changed = False
    for field in ("enabled", "emergency_kill_switch", "default_mode", "approval_timeout_minutes", "automation_policies"):
        value = getattr(payload, field)
        if value is not None:
            setattr(policy, field, value); changed = True
    if changed:
        policy.policy_version += 1
    await db.commit()
    actions = (await db.execute(select(AgentActionPolicy).where(AgentActionPolicy.governance_policy_id == policy.id).order_by(AgentActionPolicy.action_type))).scalars().all()
    return _policy_json(policy, actions)


@router.patch("/channels/{channel_id}/actions/{action_type}")
async def update_action_policy(channel_id: UUID, action_type: str, payload: ActionPolicyUpdateRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    channel = await _channel(channel_id, db, principal)
    service = AgentGovernanceService(db)
    policy = await service.ensure_policy(channel)
    action = await service.action_policy(policy, action_type)
    changed = False
    for field in ("automation_mode", "risk_tier", "enabled", "require_human_approval", "max_cost_usd", "min_confidence"):
        value = getattr(payload, field)
        if value is not None:
            setattr(action, field, value); changed = True
    if changed:
        policy.policy_version += 1
    await db.commit()
    return {"policy_version": policy.policy_version, "action": {"id": str(action.id), "action_type": action.action_type, "risk_tier": action.risk_tier, "automation_mode": action.automation_mode, "enabled": action.enabled, "require_human_approval": action.require_human_approval, "max_cost_usd": action.max_cost_usd, "min_confidence": action.min_confidence}}


@router.get("/channels/{channel_id}/approvals")
async def approval_queue(channel_id: UUID, status: str | None = None, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _channel(channel_id, db, principal)
    q = select(AgentApprovalRequest).where(AgentApprovalRequest.channel_id == channel.id).order_by(AgentApprovalRequest.requested_at.desc()).limit(200)
    if status:
        q = q.where(AgentApprovalRequest.status == status.upper())
    rows = (await db.execute(q)).scalars().all()
    return {"channel_id": str(channel.id), "approvals": [
        {"id": str(r.id), "execution_run_id": str(r.execution_run_id) if r.execution_run_id else None, "agent_task_id": str(r.agent_task_id) if r.agent_task_id else None, "status": r.status, "requested_at": r.requested_at, "expires_at": r.expires_at, "decided_by_user_id": str(r.decided_by_user_id) if r.decided_by_user_id else None, "decided_at": r.decided_at, "decision_reason": r.decision_reason, "metadata": r.metadata_json or {}}
        for r in rows
    ]}


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: UUID, payload: ApprovalDecisionRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    approval = await db.get(AgentApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(404, "Approval request not found")
    channel = await _channel(approval.channel_id, db, principal)
    result = await AgentGovernanceService(db).approve(approval=approval, principal=principal, reason=payload.reason)
    run = await db.get(AutonomousExecutionRun, approval.execution_run_id)
    if run:
        run.status = "APPROVED"
        run.reason = "Approved by human oversight."
        decision = await db.get(__import__("app.models", fromlist=["AutonomousOptimizationDecision"]).AutonomousOptimizationDecision, run.decision_id)
        if decision:
            decision.status = "APPROVED"
    await db.commit()
    return {"approval_id": str(result.id), "status": result.status, "execution_run_id": str(result.execution_run_id)}


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: UUID, payload: ApprovalDecisionRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    approval = await db.get(AgentApprovalRequest, approval_id)
    if not approval:
        raise HTTPException(404, "Approval request not found")
    await _channel(approval.channel_id, db, principal)
    result = await AgentGovernanceService(db).reject(approval=approval, principal=principal, reason=payload.reason)
    run = await db.get(AutonomousExecutionRun, approval.execution_run_id)
    if run:
        run.status = "CANCELLED"; run.reason = payload.reason or "Rejected by human oversight."
    await db.commit()
    return {"approval_id": str(result.id), "status": result.status, "execution_run_id": str(result.execution_run_id)}


@router.post("/channels/{channel_id}/kill-switch")
async def kill_switch(channel_id: UUID, enabled: bool = True, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    channel = await _channel(channel_id, db, principal)
    policy = await AgentGovernanceService(db).ensure_policy(channel)
    policy.emergency_kill_switch = enabled
    policy.policy_version += 1
    await db.commit()
    return {"channel_id": str(channel.id), "emergency_kill_switch": policy.emergency_kill_switch, "policy_version": policy.policy_version}


@router.get("/channels/{channel_id}/journal")
async def governance_journal(channel_id: UUID, limit: int = 100, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _channel(channel_id, db, principal)
    rows = (await db.execute(select(AgentGovernanceEvent).where(AgentGovernanceEvent.channel_id == channel.id).order_by(AgentGovernanceEvent.created_at.desc()).limit(min(max(limit, 1), 500)))).scalars().all()
    return {"channel_id": str(channel.id), "events": [
        {"id": str(r.id), "execution_run_id": str(r.execution_run_id) if r.execution_run_id else None, "agent_task_id": str(r.agent_task_id) if r.agent_task_id else None, "decision_id": str(r.decision_id) if r.decision_id else None, "action_type": r.action_type, "risk_tier": r.risk_tier, "event_type": r.event_type, "allowed": r.allowed, "effective_mode": r.effective_mode, "policy_version": r.policy_version, "reasons": r.reasons or [], "evaluation": r.evaluation or {}, "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None, "created_at": r.created_at}
        for r in rows
    ]}
