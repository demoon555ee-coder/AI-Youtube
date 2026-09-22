from __future__ import annotations

from datetime import datetime
from statistics import mean
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal
from app.config import settings
from app.models import (
    AgentLearningEvaluation,
    AgentLearningObservation,
    AgentStrategyProposal,
    AgentStrategyVersion,
    Channel,
)

FORBIDDEN_STRATEGY_KEYS = {
    "risk_tier", "automation_mode", "require_human_approval", "max_cost_usd",
    "min_confidence", "kill_switch", "governance", "permissions", "budget_ceiling",
}


class AgentLearningService:
    """Evidence-driven learning.

    Only durable task outcomes are authoritative evidence. Learning can propose
    bounded strategy changes, but governance remains a separate authority.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_task_outcome(self, task) -> AgentLearningObservation:
        key = f"task-outcome:{task.id}:{task.status}"
        existing = await self.db.scalar(
            select(AgentLearningObservation).where(
                AgentLearningObservation.channel_id == task.channel_id,
                AgentLearningObservation.idempotency_key == key,
            )
        )
        if existing:
            return existing

        success = task.status == "SUCCEEDED"
        requested = float(task.requested_budget_usd or 0)
        plan_id = None
        if task.plan_node_id:
            from app.models import AgentPlanNode
            node = await self.db.scalar(select(AgentPlanNode).where(AgentPlanNode.id == task.plan_node_id))
            plan_id = node.plan_id if node else None
        actual = float(task.actual_cost_usd or 0)
        efficiency = 1.0 if actual <= 0 and success else (max(0.0, 1.0 - actual / requested) if requested > 0 else 0.0)
        reward = (1.0 if success else -1.0) * (0.5 + 0.5 * efficiency)
        row = AgentLearningObservation(
            organization_id=task.organization_id,
            channel_id=task.channel_id,
            task_id=task.id,
            plan_id=plan_id,
            source_type="agent_task",
            agent_key=task.agent_key,
            action_type=task.action_type,
            outcome=task.status.lower(),
            success=success,
            reward=reward,
            cost_usd=actual,
            latency_ms=None,
            metrics={"budget_efficiency": round(efficiency, 6)},
            context={"task_type": task.task_type, "risk_tier": task.risk_tier},
            idempotency_key=key,
        )
        self.db.add(row)
        await self.db.flush()
        await self.evaluate(row)
        return row

    async def record_post_publish_feedback(
        self,
        *,
        task,
        youtube_video_id: str,
        metrics: dict,
        baseline: dict | None = None,
        source_key: str | None = None,
    ) -> AgentLearningObservation:
        """Persist post-publish performance as a durable learning observation.

        This augments, rather than replaces, the authoritative Runtime task outcome.
        Performance never changes governance controls directly.
        """
        key = f"post-publish:{task.id}:{youtube_video_id}:{source_key or metrics.get('day') or 'latest'}"
        existing = await self.db.scalar(
            select(AgentLearningObservation).where(
                AgentLearningObservation.channel_id == task.channel_id,
                AgentLearningObservation.idempotency_key == key,
            )
        )
        if existing:
            return existing

        baseline = baseline or {}
        views = float(metrics.get("views", 0) or 0)
        retention = float(metrics.get("average_view_percentage", 0) or 0)
        ctr = float(metrics.get("impression_ctr", 0) or 0)
        deltas = {}
        for name, current in (("views", views), ("average_view_percentage", retention), ("impression_ctr", ctr)):
            base = float(baseline.get(name, 0) or 0)
            deltas[name] = round((current / base - 1.0) * 100, 4) if base > 0 and current >= 0 else None
        valid_deltas = [v for v in deltas.values() if v is not None]
        mean_delta = sum(valid_deltas) / len(valid_deltas) if valid_deltas else 0.0
        reward = max(-1.0, min(1.0, mean_delta / 100.0))
        success = reward >= 0.0
        row = AgentLearningObservation(
            organization_id=task.organization_id,
            channel_id=task.channel_id,
            task_id=task.id,
            plan_id=None,
            source_type="post_publish",
            agent_key=task.agent_key,
            action_type=task.action_type,
            outcome="performance",
            success=success,
            reward=round(reward, 6),
            cost_usd=float(task.actual_cost_usd or 0),
            latency_ms=None,
            metrics={
                "youtube_video_id": youtube_video_id,
                "views": views,
                "average_view_percentage": retention,
                "impression_ctr": ctr,
                "deltas_pct": deltas,
                "mean_delta_pct": round(mean_delta, 4),
                **{k: v for k, v in metrics.items() if k not in {"views", "average_view_percentage", "impression_ctr"}},
            },
            context={"source_task_id": str(task.id), "feedback_type": "post_publish_performance"},
            idempotency_key=key,
        )
        self.db.add(row)
        await self.db.flush()
        await self.evaluate(row)
        return row

    async def evaluate(self, observation: AgentLearningObservation) -> AgentLearningEvaluation:
        existing = await self.db.scalar(
            select(AgentLearningEvaluation).where(AgentLearningEvaluation.observation_id == observation.id)
        )
        if existing:
            return existing
        efficiency = float((observation.metrics or {}).get("budget_efficiency", 0.0))
        score = max(0.0, min(1.0, 0.8 * float(observation.success) + 0.2 * efficiency))
        confidence = 0.55 if observation.success else 0.45
        rationale = [
            "Evaluation uses an authoritative task outcome.",
            "Score is bounded to success and budget efficiency.",
            "A single observation is insufficient for a strategy change.",
        ]
        row = AgentLearningEvaluation(
            organization_id=observation.organization_id,
            channel_id=observation.channel_id,
            observation_id=observation.id,
            score=score,
            confidence=confidence,
            evaluator="deterministic-v4.2.1",
            rationale=rationale,
            evidence={
                "source_type": observation.source_type,
                "success": observation.success,
                "reward": observation.reward,
                "cost_usd": observation.cost_usd,
                "metrics": observation.metrics or {},
            },
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def propose_recent(
        self,
        *,
        channel: Channel,
        agent_key: str,
        action_type: str,
        limit: int = 25,
        objective: str = "improve successful outcome rate without changing governance",
    ) -> AgentStrategyProposal:
        observations = (
            await self.db.execute(
                select(AgentLearningObservation)
                .where(
                    AgentLearningObservation.channel_id == channel.id,
                    AgentLearningObservation.agent_key == agent_key,
                    AgentLearningObservation.action_type == action_type,
                    AgentLearningObservation.source_type.in_({"agent_task", "post_publish"}),
                )
                .order_by(AgentLearningObservation.created_at.desc())
                .limit(max(settings.learning_min_observations, min(limit, 100)))
            )
        ).scalars().all()
        if len(observations) < settings.learning_min_observations:
            raise ValueError("At least 5 authoritative observations are required")
        return await self.propose(
            channel=channel,
            agent_key=agent_key,
            action_type=action_type,
            observation_ids=[o.id for o in observations],
            objective=objective,
        )

    async def propose(
        self,
        *,
        channel: Channel,
        agent_key: str,
        action_type: str,
        observation_ids: list[UUID],
        objective: str = "improve successful outcome rate without changing governance",
    ) -> AgentStrategyProposal:
        if not observation_ids:
            raise ValueError("At least one observation is required")
        observations = list(
            (
                await self.db.execute(
                    select(AgentLearningObservation).where(
                        AgentLearningObservation.channel_id == channel.id,
                        AgentLearningObservation.id.in_(observation_ids),
                        AgentLearningObservation.agent_key == agent_key,
                        AgentLearningObservation.action_type == action_type,
                        AgentLearningObservation.source_type.in_({"agent_task", "post_publish"}),
                    )
                )
            ).scalars().all()
        )
        if len(observations) < settings.learning_min_observations:
            raise ValueError("At least 5 authoritative observations are required")
        evaluations = list(
            (
                await self.db.execute(
                    select(AgentLearningEvaluation).where(
                        AgentLearningEvaluation.observation_id.in_([o.id for o in observations])
                    )
                )
            ).scalars().all()
        )
        success_rate = mean(float(o.success) for o in observations)
        avg_score = mean(float(e.score) for e in evaluations) if evaluations else 0.0
        avg_confidence = min(
            0.95,
            0.45 + 0.05 * min(len(observations), 10) + 0.2 * avg_score,
        )
        # Only one bounded, interpretable strategy parameter is learnable.
        delta = round(max(-0.15, min(0.15, (success_rate - 0.5) * 0.2)), 4)
        changes = {
            "objective": objective,
            "action_type": action_type,
            "selection_priority_delta": delta,
        }
        row = AgentStrategyProposal(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            agent_key=agent_key,
            source_observation_ids=[str(x.id) for x in observations],
            source_evaluation_ids=[str(x.id) for x in evaluations],
            status="PENDING_APPROVAL",
            proposed_changes=changes,
            expected_impact={
                "observations": len(observations),
                "success_rate": round(success_rate, 4),
                "score": round(avg_score, 4),
                "selection_priority_delta": delta,
            },
            rationale=[
                "Proposal is generated only from durable agent-task outcomes.",
                "Only selection priority can change through this learning path.",
                "Governance, permissions, budgets and risk controls are immutable here.",
            ],
            confidence=avg_confidence,
            requires_human_approval=True,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def approve_proposal(self, *, proposal, principal: Principal, reason: str = ""):
        if proposal.status != "PENDING_APPROVAL":
            raise ValueError("Strategy proposal is not pending approval")
        proposal.status = "APPROVED"
        proposal.approved_by_user_id = principal.user_id
        proposal.decided_at = datetime.utcnow()
        proposal.decision_reason = reason
        await self.db.flush()
        return proposal

    async def reject_proposal(self, *, proposal, principal: Principal, reason: str = ""):
        if proposal.status != "PENDING_APPROVAL":
            raise ValueError("Strategy proposal is not pending approval")
        proposal.status = "REJECTED"
        proposal.approved_by_user_id = principal.user_id
        proposal.decided_at = datetime.utcnow()
        proposal.decision_reason = reason
        await self.db.flush()
        return proposal

    async def activate(self, *, proposal, principal: Principal):
        if proposal.status != "APPROVED":
            raise ValueError("Only approved strategy proposals can be activated")
        latest = await self.db.scalar(
            select(AgentStrategyVersion)
            .where(
                AgentStrategyVersion.channel_id == proposal.channel_id,
                AgentStrategyVersion.agent_key == proposal.agent_key,
            )
            .order_by(AgentStrategyVersion.version.desc())
            .with_for_update()
        )
        version_number = (latest.version if latest else 0) + 1
        await self.db.execute(
            update(AgentStrategyVersion)
            .where(
                AgentStrategyVersion.channel_id == proposal.channel_id,
                AgentStrategyVersion.agent_key == proposal.agent_key,
                AgentStrategyVersion.active.is_(True),
            )
            .values(active=False)
        )
        proposed = dict(proposal.proposed_changes or {})
        proposed = {k: v for k, v in proposed.items() if k not in FORBIDDEN_STRATEGY_KEYS}
        previous = dict(latest.strategy or {}) if latest else {}
        delta = float(proposed.get("selection_priority_delta", 0.0))
        priority = max(-1.0, min(1.0, float(previous.get("selection_priority", 0.0)) + delta))
        strategy = {"selection_priority": round(priority, 4)}
        row = AgentStrategyVersion(
            organization_id=proposal.organization_id,
            channel_id=proposal.channel_id,
            agent_key=proposal.agent_key,
            version=version_number,
            source_proposal_id=proposal.id,
            strategy=strategy,
            active=True,
            activated_by_user_id=principal.user_id,
            activated_at=datetime.utcnow(),
        )
        self.db.add(row)
        proposal.status = "ACTIVATED"
        proposal.activated_at = datetime.utcnow()
        await self.db.flush()
        return row

    async def active_strategy(self, *, channel_id: UUID, agent_key: str):
        return await self.db.scalar(
            select(AgentStrategyVersion)
            .where(
                AgentStrategyVersion.channel_id == channel_id,
                AgentStrategyVersion.agent_key == agent_key,
                AgentStrategyVersion.active.is_(True),
            )
            .order_by(AgentStrategyVersion.version.desc())
        )

    @staticmethod
    def observation_json(row):
        return {
            "id": str(row.id), "agent_key": row.agent_key, "action_type": row.action_type,
            "outcome": row.outcome, "success": row.success, "reward": row.reward,
            "cost_usd": row.cost_usd, "metrics": row.metrics or {}, "created_at": row.created_at.isoformat(),
        }

    @staticmethod
    def proposal_json(row):
        return {
            "id": str(row.id), "agent_key": row.agent_key, "status": row.status,
            "confidence": row.confidence, "proposed_changes": row.proposed_changes or {},
            "expected_impact": row.expected_impact or {}, "rationale": row.rationale or [],
            "requires_human_approval": row.requires_human_approval,
            "created_at": row.created_at.isoformat(),
        }
