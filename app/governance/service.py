from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal
from app.config import settings
from app.models import AgentActionPolicy, AgentApprovalRequest, AgentGovernanceEvent, AgentGovernancePolicy

RISK_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
DEFAULT_ACTIONS = {
    "topic_scout": {"risk_tier": "LOW", "automation_mode": "auto", "require_human_approval": False, "max_cost_usd": 25.0},
    "research": {"risk_tier": "LOW", "automation_mode": "auto", "require_human_approval": False, "max_cost_usd": 25.0},
    "quality_review": {"risk_tier": "LOW", "automation_mode": "auto", "require_human_approval": False, "max_cost_usd": 25.0},
    "packaging_experiment": {"risk_tier": "LOW", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 25.0},
    "script_generation": {"risk_tier": "MEDIUM", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 50.0},
    "storyboard_generation": {"risk_tier": "MEDIUM", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 50.0},
    "production": {"risk_tier": "HIGH", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 250.0},
    "creative_direction": {"risk_tier": "MEDIUM", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 75.0},
    "scene_reedit": {"risk_tier": "MEDIUM", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 50.0},
    "blueprint_replan": {"risk_tier": "HIGH", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 100.0},
    "full_rebuild": {"risk_tier": "CRITICAL", "automation_mode": "block", "require_human_approval": True, "max_cost_usd": 250.0},
    "publish": {"risk_tier": "HIGH", "automation_mode": "approve", "require_human_approval": True, "max_cost_usd": 50.0},
}


def _requested_mode(mode: str) -> str:
    value = (mode or "approve").lower().strip()
    if value not in {"auto", "approve", "defer", "block"}:
        raise ValueError(f"Unsupported automation mode: {mode}")
    return value


class AgentGovernanceService:
    """Single authorization authority for every governed agent action."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_policy(self, channel) -> AgentGovernancePolicy:
        policy = await self.db.scalar(select(AgentGovernancePolicy).where(AgentGovernancePolicy.channel_id == channel.id).with_for_update())
        if policy:
            return policy
        policy = AgentGovernancePolicy(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            enabled=True,
            emergency_kill_switch=False,
            default_mode=settings.governance_default_mode,
            approval_timeout_minutes=settings.governance_approval_timeout_minutes,
            policy_version=1,
            automation_policies={"channel": {"enabled": True}},
        )
        self.db.add(policy)
        await self.db.flush()
        for action_type, defaults in DEFAULT_ACTIONS.items():
            self.db.add(AgentActionPolicy(
                governance_policy_id=policy.id,
                action_type=action_type,
                min_confidence=settings.optimization_min_confidence,
                **defaults,
            ))
        await self.db.flush()
        return policy

    async def action_policy(self, policy, action_type: str) -> AgentActionPolicy:
        action_type = str(action_type or "").strip()
        if not action_type:
            raise ValueError("action_type is required")
        row = await self.db.scalar(select(AgentActionPolicy).where(
            AgentActionPolicy.governance_policy_id == policy.id,
            AgentActionPolicy.action_type == action_type,
        ))
        if row:
            return row
        defaults = DEFAULT_ACTIONS.get(action_type, {
            "risk_tier": "CRITICAL",
            "automation_mode": "block",
            "require_human_approval": True,
            "max_cost_usd": 0.0,
        })
        row = AgentActionPolicy(
            governance_policy_id=policy.id,
            action_type=action_type,
            min_confidence=settings.optimization_min_confidence,
            **defaults,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def evaluate_action(
        self,
        *,
        channel,
        action_type: str,
        estimated_cost_usd: float,
        confidence: float,
        requested_mode: str,
    ) -> dict[str, Any]:
        requested = _requested_mode(requested_mode)
        policy = await self.ensure_policy(channel)
        action = await self.action_policy(policy, action_type)
        estimate = max(0.0, float(estimated_cost_usd))
        confidence = max(0.0, min(1.0, float(confidence)))
        reasons: list[str] = []
        allowed = True
        effective_mode = requested

        if not settings.governance_enabled:
            allowed = False
            effective_mode = "block"
            reasons.append("Agent Governance is disabled by configuration.")
        elif settings.governance_global_kill_switch:
            allowed = False
            effective_mode = "block"
            reasons.append("Global Agent Governance kill switch is active.")
        elif policy.emergency_kill_switch:
            allowed = False
            effective_mode = "block"
            reasons.append("Emergency kill switch is active.")
        elif not policy.enabled:
            allowed = False
            effective_mode = "block"
            reasons.append("Channel governance policy is disabled.")

        channel_automation = (policy.automation_policies or {}).get("channel") or {}
        if channel_automation.get("enabled") is False:
            allowed = False
            effective_mode = "block"
            reasons.append("Channel automation is disabled by policy.")
        if not action.enabled:
            allowed = False
            effective_mode = "block"
            reasons.append("Action is disabled by policy.")
        if estimate > float(action.max_cost_usd):
            allowed = False
            effective_mode = "block"
            reasons.append("Estimated action cost exceeds the action policy limit.")
        if confidence < float(action.min_confidence):
            allowed = False
            effective_mode = "block"
            reasons.append("Action confidence is below the policy threshold.")

        if allowed:
            if requested == "block":
                effective_mode = "block"
                reasons.append("Operator requested block.")
            elif requested == "defer":
                effective_mode = "defer"
                reasons.append("Operator requested defer.")
            elif action.automation_mode == "block":
                allowed = False
                effective_mode = "block"
                reasons.append("Action policy explicitly blocks autonomous execution.")
            elif requested == "approve" or action.require_human_approval or action.automation_mode in {"approve", "defer"}:
                effective_mode = "approve"
                reasons.append("Human approval is required by governance policy.")
            elif requested == "auto" and action.automation_mode == "auto":
                effective_mode = "auto"
                reasons.append("Action passed governance for autonomous execution.")
            elif requested == "auto":
                effective_mode = "approve"
                reasons.append("Automatic execution was downgraded to human approval by policy.")
            else:
                default_mode = _requested_mode(policy.default_mode)
                effective_mode = default_mode
                reasons.append(f"Channel default mode is {default_mode}.")

        return {
            "allowed": allowed,
            "risk_tier": action.risk_tier,
            "effective_mode": effective_mode,
            "requires_human_approval": bool(allowed and effective_mode == "approve"),
            "policy_id": str(policy.id),
            "policy_version": policy.policy_version,
            "action_policy_id": str(action.id),
            "reasons": reasons or ["Action passed governance checks."],
            "evaluation": {
                "action_type": action_type,
                "requested_mode": requested,
                "effective_mode": effective_mode,
                "estimated_cost_usd": estimate,
                "confidence": confidence,
                "global_kill_switch": settings.governance_global_kill_switch,
                "governance_enabled": settings.governance_enabled,
                "kill_switch": policy.emergency_kill_switch,
                "channel_automation_enabled": channel_automation.get("enabled", True),
                "action_automation_mode": action.automation_mode,
                "action_enabled": action.enabled,
                "max_cost_usd": action.max_cost_usd,
                "min_confidence": action.min_confidence,
                "require_human_approval": action.require_human_approval,
            },
            "policy": policy,
            "action_policy": action,
        }

    async def evaluate(self, *, channel, decision, estimate: float, principal: Principal | None, requested_mode: str) -> dict[str, Any]:
        return await self.evaluate_action(
            channel=channel,
            action_type=decision.target_scope,
            estimated_cost_usd=estimate,
            confidence=float(decision.confidence or 0),
            requested_mode=requested_mode,
        )

    async def journal(self, *, channel, decision, run, evaluation: dict, event_type: str, principal: Principal | None,
                      allowed: bool | None = None, agent_task=None) -> AgentGovernanceEvent:
        event = AgentGovernanceEvent(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            execution_run_id=run.id if run else None,
            agent_task_id=agent_task.id if agent_task else None,
            decision_id=decision.id if decision else None,
            action_type=(decision.target_scope if decision else (agent_task.action_type if agent_task else "unknown")),
            risk_tier=evaluation.get("risk_tier", "CRITICAL"),
            event_type=event_type,
            allowed=evaluation.get("allowed", False) if allowed is None else allowed,
            effective_mode=evaluation.get("effective_mode", "block"),
            policy_version=int(evaluation.get("policy_version", 1)),
            reasons=list(evaluation.get("reasons") or []),
            evaluation={k: v for k, v in evaluation.items() if k not in {"policy", "action_policy", "reasons"}},
            actor_user_id=principal.user_id if principal else None,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def create_approval(self, *, channel, run=None, task=None, evaluation: dict) -> AgentApprovalRequest:
        if bool(run) == bool(task):
            raise ValueError("Exactly one approval target is required")
        target_id = run.id if run else task.id
        target_field = AgentApprovalRequest.execution_run_id if run else AgentApprovalRequest.agent_task_id
        existing = await self.db.scalar(
            select(AgentApprovalRequest)
            .where(target_field == target_id, AgentApprovalRequest.status == "PENDING")
            .order_by(AgentApprovalRequest.requested_at.desc())
        )
        if existing:
            existing_version = int((existing.metadata_json or {}).get("policy_version", 0))
            if existing_version == int(evaluation["policy_version"]):
                return existing
            existing.status = "SUPERSEDED"
            existing.decided_at = datetime.utcnow()
            existing.decision_reason = "Superseded by a newer governance policy version."
            await self.db.flush()
        policy = evaluation["policy"]
        approval = AgentApprovalRequest(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            execution_run_id=run.id if run else None,
            agent_task_id=task.id if task else None,
            status="PENDING",
            expires_at=datetime.utcnow() + timedelta(minutes=max(1, int(policy.approval_timeout_minutes))),
            metadata_json={
                "risk_tier": evaluation["risk_tier"],
                "reasons": evaluation["reasons"],
                "policy_version": evaluation["policy_version"],
                "action_type": evaluation["evaluation"]["action_type"],
            },
        )
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def approve(self, *, approval, principal: Principal, reason: str = ""):
        if approval.status != "PENDING":
            raise ValueError("Approval request is not pending")
        if approval.expires_at and approval.expires_at <= datetime.utcnow():
            approval.status = "EXPIRED"
            await self.db.flush()
            raise ValueError("Approval request has expired")
        approval.status = "APPROVED"
        approval.decided_by_user_id = principal.user_id
        approval.decided_at = datetime.utcnow()
        approval.decision_reason = reason
        if approval.agent_task_id:
            from app.models import AgentTask
            task = await self.db.scalar(select(AgentTask).where(AgentTask.id == approval.agent_task_id).with_for_update())
            if not task:
                raise ValueError("Approval target task not found")
            if task.status != "PENDING_APPROVAL":
                raise ValueError("Approval target task is no longer awaiting approval")
            task.governance_approved = True
            task.status = "PENDING"
            if task.plan_node_id:
                from app.models import AgentPlanNode
                node = await self.db.scalar(select(AgentPlanNode).where(AgentPlanNode.id == task.plan_node_id).with_for_update())
                if node:
                    node.status = "READY"
        await self.db.flush()
        return approval

    async def reject(self, *, approval, principal: Principal, reason: str = ""):
        if approval.status != "PENDING":
            raise ValueError("Approval request is not pending")
        approval.status = "REJECTED"
        approval.decided_by_user_id = principal.user_id
        approval.decided_at = datetime.utcnow()
        approval.decision_reason = reason
        if approval.agent_task_id:
            from app.models import AgentTask
            task = await self.db.scalar(select(AgentTask).where(AgentTask.id == approval.agent_task_id).with_for_update())
            if task:
                task.status = "BLOCKED"
                task.governance_approved = False
                if task.plan_node_id:
                    from app.models import AgentPlanNode
                    node = await self.db.scalar(select(AgentPlanNode).where(AgentPlanNode.id == task.plan_node_id).with_for_update())
                    if node:
                        node.status = "BLOCKED"
        await self.db.flush()
        return approval

