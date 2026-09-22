from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.service import AgentGovernanceService
from app.models.agent_runtime import (
    AgentBudgetLedger,
    AgentDefinition,
    AgentHandoff,
    AgentLease,
    AgentTask,
    AgentTaskDependency,
)


DEFAULT_AGENTS = {
    "scout": {
        "display_name": "Topic Scout Agent",
        "capabilities": ["scout", "topic_scout", "trend_analysis"],
        "max_concurrency": 2,
    },
    "research": {
        "display_name": "Research Agent",
        "capabilities": ["research", "trend_analysis", "source_validation"],
        "max_concurrency": 2,
    },
    "script": {
        "display_name": "Script Agent",
        "capabilities": ["script", "script_generation", "script_revision", "storytelling"],
        "max_concurrency": 2,
    },
    "storyboard": {
        "display_name": "Storyboard Agent",
        "capabilities": ["storyboard", "storyboarding"],
        "max_concurrency": 2,
    },
    "scene_director": {
        "display_name": "Scene Director Agent",
        "capabilities": ["scene_director", "creative_direction", "scene_direction"],
        "max_concurrency": 2,
    },
    "production": {
        "display_name": "Production Agent",
        "capabilities": ["production", "scene_reedit", "packaging_experiment"],
        "max_concurrency": 1,
    },
    "qa": {
        "display_name": "Quality Agent",
        "capabilities": ["qa", "quality_review", "policy_check", "fact_check"],
        "max_concurrency": 3,
    },
    "publisher": {
        "display_name": "YouTube Publisher Agent",
        "capabilities": ["publisher", "publish"],
        "max_concurrency": 1,
    },
}


class AgentRuntimeError(ValueError):
    pass


class AgentRuntimeService:
    """Durable task runtime used by the planner and internal workers.

    This service is intentionally not a second execution engine. It owns task
    lifecycle, lease integrity, lineage, budgeting, governance admission and
    outcome publication. Actual work is performed by a worker implementation.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.governance = AgentGovernanceService(db)

    async def ensure_agents(self, channel_id: str) -> None:
        existing = {
            row.agent_key: row
            for row in (
                await self.db.execute(
                    select(AgentDefinition).where(AgentDefinition.channel_id == channel_id)
                )
            ).scalars().all()
        }
        for key, cfg in DEFAULT_AGENTS.items():
            row = existing.get(key)
            if row is None:
                row = AgentDefinition(
                    organization_id=(await self._get_channel(channel_id)).organization_id,
                    channel_id=channel_id,
                    agent_key=key,
                    display_name=cfg["display_name"],
                    capabilities=list(cfg["capabilities"]),
                    max_concurrency=cfg["max_concurrency"],
                    enabled=True,
                )
                self.db.add(row)
            else:
                row.display_name = cfg["display_name"]
                row.capabilities = list(cfg["capabilities"])
                row.max_concurrency = cfg["max_concurrency"]
        await self.db.flush()

    async def _get_agent(self, channel_id: str, agent_key: str, *, lock: bool = False) -> AgentDefinition:
        stmt = select(AgentDefinition).where(
            AgentDefinition.channel_id == channel_id,
            AgentDefinition.agent_key == agent_key,
        )
        if lock:
            stmt = stmt.with_for_update()
        agent = (await self.db.execute(stmt)).scalar_one_or_none()
        if not agent:
            raise AgentRuntimeError("agent_not_found")
        if not agent.enabled:
            raise AgentRuntimeError("agent_disabled")
        return agent

    async def _assert_same_channel_task(self, task_id: str | None, channel_id: str) -> AgentTask | None:
        if not task_id:
            return None
        task = (
            await self.db.execute(
                select(AgentTask).where(
                    AgentTask.id == task_id,
                    AgentTask.channel_id == channel_id,
                )
            )
        ).scalar_one_or_none()
        if not task:
            raise AgentRuntimeError("parent_task_not_found")
        return task

    async def _validate_dependencies(
        self,
        channel_id: str,
        task_id: str | None,
        dependency_ids: list[str],
    ) -> list[AgentTask]:
        unique_ids = list(dict.fromkeys(dependency_ids))
        if task_id and task_id in unique_ids:
            raise AgentRuntimeError("task_dependency_cycle")
        if not unique_ids:
            return []
        rows = (
            await self.db.execute(
                select(AgentTask).where(
                    AgentTask.id.in_(unique_ids),
                    AgentTask.channel_id == channel_id,
                )
            )
        ).scalars().all()
        if len(rows) != len(unique_ids):
            raise AgentRuntimeError("dependency_not_found")
        return rows

    async def _would_create_cycle(self, task_id: str, dependency_ids: list[str]) -> bool:
        """Bounded DFS over existing dependency edges."""
        if not dependency_ids:
            return False
        graph: dict[str, list[str]] = {}
        rows = (
            await self.db.execute(select(AgentTaskDependency))
        ).scalars().all()
        for edge in rows:
            graph.setdefault(edge.task_id, []).append(edge.depends_on_task_id)
        frontier = list(dependency_ids)
        seen: set[str] = set()
        while frontier:
            current = frontier.pop()
            if current == task_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(graph.get(current, []))
        return False

    async def create_task(
        self,
        *,
        channel_id: str,
        agent_key: str,
        task_type: str,
        action_type: str | None,
        input_data: dict | None,
        budget_usd: Decimal,
        priority: int = 100,
        parent_task_id: str | None = None,
        dependencies: list[str] | None = None,
        idempotency_key: str | None = None,
        confidence: float = 0.0,
        requested_mode: str = "auto",
        plan_node_id: str | None = None,
        workflow_run_id: str | None = None,
        project_id: str | None = None,
    ) -> AgentTask:
        if budget_usd < Decimal("0"):
            raise AgentRuntimeError("invalid_budget")
        if not action_type:
            raise AgentRuntimeError("action_type_required")
        await self.ensure_agents(channel_id)
        agent = await self._get_agent(channel_id, agent_key)
        if task_type not in (agent.capabilities or []) and task_type != agent.agent_key:
            raise AgentRuntimeError("task_type_not_supported_by_agent")
        parent = await self._assert_same_channel_task(parent_task_id, channel_id)
        dependency_rows = await self._validate_dependencies(channel_id, None, dependencies or [])

        idempotency_key = idempotency_key or f"runtime:{uuid4().hex}"
        if idempotency_key:
            existing = (
                await self.db.execute(
                    select(AgentTask).where(
                        AgentTask.channel_id == channel_id,
                        AgentTask.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return existing

        channel = await self._get_channel(channel_id)
        evaluation = await self.governance.evaluate_action(
            channel=channel,
            action_type=action_type,
            estimated_cost_usd=budget_usd,
            confidence=confidence,
            requested_mode=requested_mode,
        )

        status = "PENDING"
        governance_approved = evaluation["effective_mode"] == "auto"
        if not evaluation["allowed"] or evaluation["effective_mode"] in {"block", "defer"}:
            status = "BLOCKED"
            governance_approved = False
        elif evaluation["effective_mode"] == "approve":
            status = "PENDING_APPROVAL"
            governance_approved = False

        task = AgentTask(
            channel_id=channel_id,
            organization_id=channel.organization_id,
            project_id=project_id,
            plan_node_id=plan_node_id,
            workflow_run_id=workflow_run_id,
            parent_task_id=parent.id if parent else None,
            agent_key=agent.agent_key,
            task_type=task_type,
            action_type=action_type,
            risk_tier=evaluation["risk_tier"],
            governance_mode=evaluation["effective_mode"],
            governance_approved=governance_approved,
            governance_policy_version=evaluation["policy_version"],
            confidence=float(confidence),
            input_data=input_data or {},
            status=status,
            priority=priority,
            requested_budget_usd=budget_usd,
            idempotency_key=idempotency_key,
        )
        self.db.add(task)
        await self.db.flush()

        if await self._would_create_cycle(task.id, [row.id for row in dependency_rows]):
            raise AgentRuntimeError("task_dependency_cycle")
        for row in dependency_rows:
            self.db.add(
                AgentTaskDependency(task_id=task.id, depends_on_task_id=row.id)
            )

        await self.governance.journal(
            channel=channel,
            decision=None,
            run=None,
            evaluation=evaluation,
            event_type="TASK_ADMITTED",
            principal=None,
            agent_task=task,
        )
        if status == "PENDING_APPROVAL":
            await self.governance.create_approval(
                channel=channel,
                task=task,
                evaluation=evaluation,
            )
        await self._sync_plan_node(task)
        return task

    async def _get_channel(self, channel_id: str):
        from app.models.channel import Channel

        channel = (
            await self.db.execute(select(Channel).where(Channel.id == channel_id))
        ).scalar_one_or_none()
        if not channel:
            raise AgentRuntimeError("channel_not_found")
        return channel

    async def readiness(self, task: AgentTask) -> bool:
        if task.status != "PENDING" or not task.governance_approved:
            return False
        if not task.action_type:
            return False
        dependency_statuses = (
            await self.db.execute(
                select(AgentTask.status)
                .join(
                    AgentTaskDependency,
                    AgentTaskDependency.depends_on_task_id == AgentTask.id,
                )
                .where(AgentTaskDependency.task_id == task.id)
            )
        ).scalars().all()
        return all(status == "SUCCEEDED" for status in dependency_statuses)

    async def acquire_lease(
        self,
        *,
        task_id: str,
        agent_key: str,
        ttl_seconds: int = 300,
    ) -> AgentLease:
        task = (
            await self.db.execute(
                select(AgentTask).where(AgentTask.id == task_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not task:
            raise AgentRuntimeError("task_not_found")
        if task.agent_key != agent_key:
            raise AgentRuntimeError("agent_mismatch")
        agent = await self._get_agent(task.channel_id, agent_key, lock=True)

        # Re-admit against the current policy immediately before execution.
        channel = await self._get_channel(task.channel_id)
        evaluation = await self.governance.evaluate_action(
            channel=channel,
            action_type=task.action_type or task.task_type,
            estimated_cost_usd=task.requested_budget_usd,
            confidence=task.confidence,
            requested_mode="auto",
        )
        task.risk_tier = evaluation["risk_tier"]
        task.governance_mode = evaluation["effective_mode"]
        if not evaluation["allowed"]:
            task.status = "BLOCKED"
            task.governance_approved = False
            await self.governance.journal(channel=channel, decision=None, run=None, evaluation=evaluation, event_type="EXECUTION_RECHECK", principal=None, agent_task=task)
            await self._sync_plan_node(task)
            raise AgentRuntimeError("governance_blocked")
        policy_changed = task.governance_policy_version != evaluation["policy_version"]
        if evaluation["effective_mode"] == "approve" and (not task.governance_approved or policy_changed):
            task.status = "PENDING_APPROVAL"
            task.governance_approved = False
            task.governance_policy_version = evaluation["policy_version"]
            await self.governance.create_approval(channel=channel, task=task, evaluation=evaluation)
            await self.governance.journal(
                channel=channel, decision=None, run=None, evaluation=evaluation,
                event_type="EXECUTION_RECHECK", principal=None, agent_task=task,
            )
            await self._sync_plan_node(task)
            raise AgentRuntimeError("approval_required")
        task.governance_policy_version = evaluation["policy_version"]
        task.governance_approved = True
        if not await self.readiness(task):
            raise AgentRuntimeError("task_not_ready")

        existing_lease = await self.db.scalar(select(AgentLease).where(AgentLease.task_id == task.id).with_for_update())
        if existing_lease:
            if existing_lease.expires_at <= datetime.utcnow():
                await self.db.delete(existing_lease)
                task.status = "PENDING"
                await self.db.flush()
            else:
                raise AgentRuntimeError("task_already_leased")

        active_lease_count = (
            await self.db.execute(
                select(func.count(AgentLease.id)).where(
                    AgentLease.channel_id == task.channel_id,
                    AgentLease.agent_key == agent_key,
                    AgentLease.expires_at > datetime.utcnow(),
                )
            )
        ).scalar_one()
        if active_lease_count >= agent.max_concurrency:
            raise AgentRuntimeError("agent_concurrency_limit")

        now = datetime.utcnow()
        lease = AgentLease(
            task_id=task.id,
            channel_id=task.channel_id,
            agent_key=agent_key,
            lease_token=uuid4().hex,
            acquired_at=now,
            expires_at=now + timedelta(seconds=max(30, ttl_seconds)),
        )
        task.status = "RUNNING"
        task.started_at = task.started_at or now
        self.db.add(lease)
        await self.db.flush()
        if task.requested_budget_usd > 0 and task.reserved_budget_usd <= 0:
            await self._reserve_budget_locked(task, Decimal(str(task.requested_budget_usd)))
        await self._sync_plan_node(task)
        return lease

    async def _get_live_lease(self, task_id: str, lease_token: str, *, lock: bool = True) -> AgentLease:
        stmt = select(AgentLease).where(
            AgentLease.task_id == task_id,
            AgentLease.lease_token == lease_token,
        )
        if lock:
            stmt = stmt.with_for_update()
        lease = (await self.db.execute(stmt)).scalar_one_or_none()
        if not lease:
            raise AgentRuntimeError("invalid_lease")
        if lease.expires_at <= datetime.utcnow():
            raise AgentRuntimeError("lease_expired")
        return lease

    async def heartbeat(self, *, task_id: str, lease_token: str, ttl_seconds: int = 300) -> AgentLease:
        lease = await self._get_live_lease(task_id, lease_token)
        now = datetime.utcnow()
        lease.heartbeat_at = now
        lease.expires_at = now + timedelta(seconds=max(30, ttl_seconds))
        return lease

    async def complete(
        self,
        *,
        task_id: str,
        lease_token: str,
        output_data: dict | None,
        actual_cost_usd: Decimal,
    ) -> AgentTask:
        if actual_cost_usd < Decimal("0"):
            raise AgentRuntimeError("invalid_actual_cost")
        task = (
            await self.db.execute(select(AgentTask).where(AgentTask.id == task_id).with_for_update())
        ).scalar_one_or_none()
        if not task:
            raise AgentRuntimeError("task_not_found")
        await self._get_live_lease(task_id, lease_token)
        if task.status != "RUNNING":
            raise AgentRuntimeError("task_not_running")
        if actual_cost_usd > task.requested_budget_usd:
            task.status = "FAILED"
            raise AgentRuntimeError("budget_exceeded")

        task.status = "SUCCEEDED"
        task.output_data = output_data or {}
        task.actual_cost_usd = actual_cost_usd
        task.completed_at = datetime.utcnow()
        await self._settle_reservation(task, actual_cost_usd)
        await self._delete_lease(task_id, lease_token)
        await self._record_outcome(task)
        await self._sync_plan_node(task)
        return task

    async def fail(
        self,
        *,
        task_id: str,
        lease_token: str,
        error: dict | str,
    ) -> AgentTask:
        task = (
            await self.db.execute(select(AgentTask).where(AgentTask.id == task_id).with_for_update())
        ).scalar_one_or_none()
        if not task:
            raise AgentRuntimeError("task_not_found")
        await self._get_live_lease(task_id, lease_token)
        if task.status != "RUNNING":
            raise AgentRuntimeError("task_not_running")
        task.status = "FAILED"
        task.error_message = error if isinstance(error, str) else str(error)
        task.completed_at = datetime.utcnow()
        await self._settle_reservation(task, Decimal("0"))
        await self._delete_lease(task_id, lease_token)
        await self._record_outcome(task)
        await self._sync_plan_node(task)
        return task

    async def recover_expired_leases(self) -> int:
        now = datetime.utcnow()
        leases = (
            await self.db.execute(select(AgentLease).where(AgentLease.expires_at <= now).with_for_update())
        ).scalars().all()
        recovered = 0
        for lease in leases:
            task = (
                await self.db.execute(select(AgentTask).where(AgentTask.id == lease.task_id).with_for_update())
            ).scalar_one_or_none()
            if task and task.status == "RUNNING":
                task.status = "PENDING"
                recovered += 1
                await self._sync_plan_node(task)
            await self.db.delete(lease)
        return recovered

    async def _delete_lease(self, task_id: str, lease_token: str) -> None:
        lease = await self._get_live_lease(task_id, lease_token)
        await self.db.delete(lease)
        await self.db.flush()

    async def _reserve_budget_locked(self, task: AgentTask, amount_usd: Decimal) -> AgentBudgetLedger:
        if amount_usd <= Decimal("0"):
            raise AgentRuntimeError("invalid_budget_reservation")
        prior = Decimal(str(task.reserved_budget_usd or 0))
        if prior + amount_usd > Decimal(str(task.requested_budget_usd)):
            raise AgentRuntimeError("budget_already_reserved")
        entry = AgentBudgetLedger(
            organization_id=task.organization_id,
            channel_id=task.channel_id,
            task_id=task.id,
            agent_key=task.agent_key,
            entry_type="RESERVE",
            amount_usd=amount_usd,
            balance_after_usd=prior + amount_usd,
        )
        task.reserved_budget_usd = float(prior + amount_usd)
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def reserve_budget(self, *, task_id: str, amount_usd: Decimal) -> AgentBudgetLedger:
        task = (
            await self.db.execute(select(AgentTask).where(AgentTask.id == task_id).with_for_update())
        ).scalar_one_or_none()
        if not task:
            raise AgentRuntimeError("task_not_found")
        return await self._reserve_budget_locked(task, amount_usd)

    async def _settle_reservation(self, task: AgentTask, actual_cost_usd: Decimal) -> None:
        reserved = Decimal(str(task.reserved_budget_usd or 0))
        unused = max(Decimal("0"), reserved - actual_cost_usd)
        if unused > 0:
            balance_after = max(Decimal("0"), reserved - unused)
            self.db.add(AgentBudgetLedger(
                organization_id=task.organization_id,
                channel_id=task.channel_id,
                task_id=task.id,
                agent_key=task.agent_key,
                entry_type="RELEASE",
                amount_usd=-unused,
                balance_after_usd=balance_after,
                metadata_json={"actual_cost_usd": float(actual_cost_usd)},
            ))
        task.reserved_budget_usd = 0.0
        await self.db.flush()

    async def handoff(self, *, task: AgentTask, target_agent_key: str, lease_token: str, reason: str, payload: dict | None = None) -> AgentHandoff:
        await self._get_live_lease(task.id, lease_token)
        await self._get_agent(task.channel_id, target_agent_key)
        handoff = AgentHandoff(
            channel_id=task.channel_id,
            task_id=task.id,
            from_agent=task.agent_key,
            to_agent=target_agent_key,
            reason=reason,
            payload=payload or {},
        )
        self.db.add(handoff)
        await self.db.flush()
        return handoff

    async def delegate(
        self,
        *,
        task: AgentTask,
        target_agent_key: str,
        lease_token: str,
        task_type: str,
        action_type: str,
        input_data: dict | None,
        budget_usd: Decimal,
        priority: int = 100,
    ) -> AgentTask:
        await self._get_live_lease(task.id, lease_token)
        child = await self.create_task(
            channel_id=task.channel_id,
            agent_key=target_agent_key,
            task_type=task_type,
            action_type=action_type,
            input_data=input_data,
            budget_usd=budget_usd,
            priority=priority,
            parent_task_id=task.id,
            dependencies=[],
            requested_mode="auto",
        )
        return child

    async def queue(self, channel_id: str, limit: int = 100) -> list[AgentTask]:
        return (
            await self.db.execute(
                select(AgentTask)
                .where(
                    AgentTask.channel_id == channel_id,
                    AgentTask.status.in_(["PENDING", "PENDING_APPROVAL"]),
                )
                .order_by(AgentTask.priority.desc(), AgentTask.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()

    async def _record_outcome(self, task: AgentTask) -> None:
        from app.learning.service import AgentLearningService

        await AgentLearningService(self.db).record_task_outcome(task)

    async def _sync_plan_node(self, task: AgentTask) -> None:
        if not task.plan_node_id:
            return
        from app.models.planner import AgentPlanNode

        node = (
            await self.db.execute(
                select(AgentPlanNode).where(AgentPlanNode.id == task.plan_node_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not node:
            return
        mapping = {
            "PENDING_APPROVAL": "PENDING_APPROVAL",
            "PENDING": "READY",
            "RUNNING": "RUNNING",
            "SUCCEEDED": "SUCCEEDED",
            "FAILED": "FAILED",
            "BLOCKED": "BLOCKED",
            "CANCELLED": "CANCELLED",
        }
        node.status = mapping.get(task.status, node.status)
        node.task_id = task.id
        if task.output_data:
            node.output_data = task.output_data
        if task.error_message:
            node.rationale = f"Execution failed: {task.error_message}"
        from app.models.planner import AgentPlan, AgentPlanNode as PlanNode
        plan = await self.db.get(AgentPlan, node.plan_id)
        if plan:
            plan_nodes = (await self.db.execute(select(PlanNode).where(PlanNode.plan_id == plan.id))).scalars().all()
            if any(n.status == "BLOCKED" for n in plan_nodes):
                plan.status = "BLOCKED"
            elif plan_nodes and all(n.status == "SUCCEEDED" for n in plan_nodes):
                plan.status = "COMPLETED"
            elif any(n.status == "PENDING_APPROVAL" for n in plan_nodes):
                plan.status = "AWAITING_APPROVAL"
            elif any(n.status in {"RUNNING", "READY", "PLANNED"} for n in plan_nodes):
                plan.status = "RUNNING"
            elif any(n.status == "FAILED" for n in plan_nodes):
                plan.status = "FAILED"

