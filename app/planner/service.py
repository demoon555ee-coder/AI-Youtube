from __future__ import annotations

from collections import defaultdict, deque
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

from app.governance.service import AgentGovernanceService
from app.learning.service import AgentLearningService
from app.models import (
    AgentDefinition,
    AgentPlan,
    AgentPlanEdge,
    AgentPlanEvent,
    AgentPlanNode,
    AgentTask,
    Channel,
)
from app.runtime.service import AgentRuntimeError, AgentRuntimeService


DEFAULT_BLUEPRINT = [
    {"node_key": "scout", "capability": "topic_scout", "task_type": "scout", "action_type": "topic_scout", "cost": 0.8, "confidence": 0.82, "deps": []},
    {"node_key": "research", "capability": "research", "task_type": "research", "action_type": "research", "cost": 1.5, "confidence": 0.86, "deps": ["scout"]},
    {"node_key": "script", "capability": "script_generation", "task_type": "script", "action_type": "script_generation", "cost": 3.0, "confidence": 0.88, "deps": ["research"]},
    {"node_key": "storyboard", "capability": "storyboard", "task_type": "storyboard", "action_type": "storyboard_generation", "cost": 2.0, "confidence": 0.86, "deps": ["script"]},
    {"node_key": "scene_director", "capability": "creative_direction", "task_type": "scene_director", "action_type": "creative_direction", "cost": 3.0, "confidence": 0.82, "deps": ["storyboard"]},
    {"node_key": "production", "capability": "production", "task_type": "production", "action_type": "production", "cost": 12.0, "confidence": 0.79, "deps": ["scene_director"]},
    {"node_key": "qa", "capability": "quality_review", "task_type": "qa", "action_type": "quality_review", "cost": 2.0, "confidence": 0.91, "deps": ["production"]},
    {"node_key": "publish", "capability": "publish", "task_type": "publisher", "action_type": "publish", "cost": 0.5, "confidence": 0.90, "deps": ["qa"]},
]


class AgentPlannerService:
    """Single durable planner layered above the governed task runtime."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = settings
        self.runtime = AgentRuntimeService(db)
        self.governance = AgentGovernanceService(db)
        self.learning = AgentLearningService(db)

    async def create_plan(
        self,
        *,
        channel: Channel,
        goal: str,
        context: dict | None = None,
        budget_usd: float = 0.0,
        project_id: UUID | None = None,
        blueprint: list[dict] | None = None,
    ) -> AgentPlan:
        if not goal.strip():
            raise ValueError("Plan goal cannot be empty")
        if budget_usd < 0:
            raise ValueError("Plan budget cannot be negative")
        plan = AgentPlan(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            project_id=project_id,
            goal=goal.strip(),
            budget_usd=float(budget_usd),
            context=context or {},
            status="DRAFT",
        )
        self.db.add(plan)
        await self.db.flush()
        await self._build(plan, channel, blueprint or self._blueprint_for(context or {}))
        await self._event(plan, "PLAN_CREATED", payload={"goal": plan.goal})
        return plan

    def _blueprint_for(self, context: dict) -> list[dict]:
        requested = context.get("steps")
        return [dict(x) for x in requested] if requested else [dict(x) for x in DEFAULT_BLUEPRINT]

    async def _build(self, plan: AgentPlan, channel: Channel, specs: list[dict]) -> None:
        await self.runtime.ensure_agents(channel.id)
        agents = (await self.db.execute(select(AgentDefinition).where(AgentDefinition.channel_id == channel.id, AgentDefinition.enabled.is_(True)))).scalars().all()
        by_cap = defaultdict(list)
        for agent in agents:
            for cap in agent.capabilities or []:
                by_cap[str(cap)].append(agent)

        self._validate_acyclic(specs)
        nodes: dict[str, AgentPlanNode] = {}
        total = 0.0
        confidences: list[float] = []
        governance_snapshot: dict[str, Any] = {}
        strategy_snapshot: dict[str, Any] = {}

        for raw in specs:
            key = str(raw.get("node_key") or raw.get("task_type") or "node").strip()
            if key in nodes:
                raise ValueError(f"Duplicate plan node: {key}")
            capability = str(raw.get("capability") or raw.get("requested_capability") or raw.get("task_type") or "").strip()
            candidates = by_cap.get(capability, []) or [a for a in agents if a.agent_key == capability]
            if not candidates:
                raise ValueError(f"No enabled agent matches capability '{capability}'")
            cost = max(0.0, float(raw.get("cost", raw.get("estimated_cost_usd", 0.0))))
            confidence = min(1.0, max(0.0, float(raw.get("confidence", 0.75))))
            action_type = str(raw.get("action_type") or raw.get("task_type") or capability)

            ranked = []
            for agent in candidates:
                strategy = await self.learning.active_strategy(channel_id=channel.id, agent_key=agent.agent_key)
                selection_priority = float((strategy.strategy or {}).get("selection_priority", 0.0)) if strategy else 0.0
                strategy_snapshot[agent.agent_key] = {"version": strategy.version, "strategy": strategy.strategy or {}} if strategy else {"version": 0, "strategy": {}}
                ranked.append((self._agent_score(agent, raw, selection_priority), agent))
            _, agent = max(ranked, key=lambda pair: pair[0])

            gov = await self.governance.evaluate_action(
                channel=channel,
                action_type=action_type,
                estimated_cost_usd=cost,
                confidence=confidence,
                requested_mode="auto",
            )
            status = "BLOCKED" if not gov["allowed"] else ("PENDING_APPROVAL" if gov["effective_mode"] == "approve" else "PLANNED")
            node = AgentPlanNode(
                plan_id=plan.id,
                node_key=key,
                status=status,
                requested_capability=capability,
                agent_key=agent.agent_key,
                task_type=str(raw.get("task_type") or capability),
                action_type=action_type,
                estimated_cost_usd=cost,
                confidence=confidence,
                requires_approval=gov["requires_human_approval"],
                governance_mode=gov["effective_mode"],
                risk_tier=gov["risk_tier"],
                governance_policy_version=gov["policy_version"],
                rationale=" ".join(gov["reasons"]),
                input_data=raw.get("input_data") or {},
            )
            self.db.add(node)
            await self.db.flush()
            nodes[key] = node
            total += cost
            confidences.append(confidence)
            governance_snapshot[key] = {
                "allowed": gov["allowed"],
                "risk_tier": gov["risk_tier"],
                "effective_mode": gov["effective_mode"],
                "policy_version": gov["policy_version"],
                "reasons": gov["reasons"],
            }

        for raw in specs:
            key = str(raw.get("node_key") or raw.get("task_type") or "node").strip()
            node = nodes[key]
            for dep_key in raw.get("deps", raw.get("dependencies", [])) or []:
                if dep_key not in nodes:
                    raise ValueError(f"Unknown dependency '{dep_key}' for node '{key}'")
                self.db.add(AgentPlanEdge(plan_id=plan.id, from_node_id=nodes[dep_key].id, to_node_id=node.id))
        await self.db.flush()

        plan.estimated_cost_usd = total
        plan.confidence = sum(confidences) / len(confidences) if confidences else 0.0
        plan.governance_snapshot = governance_snapshot
        plan.strategy = strategy_snapshot
        plan.rationale = [
            "Goal decomposed into a durable DAG.",
            "Agents selected by capability plus approved strategy preference.",
            "Each node was admitted by the same governance authority used immediately before execution.",
        ]
        if plan.budget_usd > 0 and total > plan.budget_usd:
            plan.status = "BLOCKED"
            plan.rationale.append("Estimated plan cost exceeds the supplied budget ceiling.")
            for node in nodes.values():
                if node.status == "PLANNED":
                    node.status = "BLOCKED"
        elif any(n.status == "BLOCKED" for n in nodes.values()):
            plan.status = "BLOCKED"
        elif any(n.status == "PENDING_APPROVAL" for n in nodes.values()):
            plan.status = "AWAITING_APPROVAL"
        else:
            plan.status = "PLANNED"

    @staticmethod
    def _agent_score(agent, raw: dict, strategy_priority: float) -> float:
        score = strategy_priority
        if raw.get("preferred_agent") == agent.agent_key:
            score += 0.25
        capability_count = len(agent.capabilities or [])
        score += min(0.10, capability_count / 100.0)
        return score

    @staticmethod
    def _validate_acyclic(specs: list[dict]) -> None:
        graph = {
            str(s.get("node_key") or s.get("task_type") or "node"): set(s.get("deps", s.get("dependencies", [])) or [])
            for s in specs
        }
        indegree = {k: len(v) for k, v in graph.items()}
        children = defaultdict(list)
        for node, deps in graph.items():
            for dep in deps:
                if dep not in graph:
                    raise ValueError(f"Unknown dependency '{dep}' for node '{node}'")
                children[dep].append(node)
        queue = deque(k for k, degree in indegree.items() if degree == 0)
        seen = 0
        while queue:
            cur = queue.popleft()
            seen += 1
            for child in children[cur]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if seen != len(graph):
            raise ValueError("Plan graph contains a cycle")

    async def _sync_from_tasks(self, plan: AgentPlan) -> None:
        nodes = (await self.db.execute(select(AgentPlanNode).where(AgentPlanNode.plan_id == plan.id))).scalars().all()
        for node in nodes:
            if not node.task_id:
                continue
            task = await self.db.get(AgentTask, node.task_id)
            if not task:
                continue
            await self.runtime._sync_plan_node(task)
        await self._refresh_plan_status(plan)

    async def readiness(self, plan: AgentPlan) -> list[AgentPlanNode]:
        await self._sync_from_tasks(plan)
        nodes = list((await self.db.execute(select(AgentPlanNode).where(AgentPlanNode.plan_id == plan.id))).scalars().all())
        edges = list((await self.db.execute(select(AgentPlanEdge).where(AgentPlanEdge.plan_id == plan.id))).scalars().all())
        by_id = {n.id: n for n in nodes}
        deps = defaultdict(list)
        for e in edges:
            deps[e.to_node_id].append(e.from_node_id)
        return [n for n in nodes if n.task_id is None and n.status in {"PLANNED", "PENDING_APPROVAL"} and all(by_id[d].status == "SUCCEEDED" for d in deps[n.id])]

    @staticmethod
    def _compose_task_input(
        plan: AgentPlan,
        node: AgentPlanNode,
        dependency_nodes: list[AgentPlanNode],
    ) -> dict[str, Any]:
        """Build deterministic task input from plan context plus completed upstream outputs.

        Upstream data is namespaced by node key to prevent accidental field collisions.
        The scout result also promotes topic/keywords/trend_score because the existing
        research capability consumes those fields directly.
        """
        task_input = {**(plan.context or {}), **(node.input_data or {})}
        upstream_outputs: dict[str, Any] = {}
        for dep in dependency_nodes:
            output = dict(dep.output_data or {})
            upstream_outputs[dep.node_key] = output
            task_input[dep.node_key] = output
            if dep.node_key == "scout":
                for field in ("topic", "keywords", "trend_score"):
                    if field in output and field not in task_input:
                        task_input[field] = output[field]
        task_input["upstream_outputs"] = upstream_outputs
        task_input["plan_id"] = str(plan.id)
        task_input["plan_node_id"] = str(node.id)
        return task_input

    async def materialize_ready(self, plan: AgentPlan) -> list[AgentPlanNode]:
        await self._sync_from_tasks(plan)
        if plan.status in {"BLOCKED", "CANCELLED", "FAILED", "COMPLETED"}:
            return []
        ready = await self.readiness(plan)
        all_nodes = list((await self.db.execute(select(AgentPlanNode).where(AgentPlanNode.plan_id == plan.id))).scalars().all())
        by_id = {n.id: n for n in all_nodes}
        edges = list((await self.db.execute(select(AgentPlanEdge).where(AgentPlanEdge.plan_id == plan.id))).scalars().all())
        dep_tasks = defaultdict(list)
        for edge in edges:
            dep = by_id[edge.from_node_id]
            if dep.task_id:
                dep_tasks[edge.to_node_id].append(dep.task_id)

        created: list[AgentPlanNode] = []
        channel = await self.db.get(Channel, plan.channel_id)
        for node in ready:
            if node.task_id:
                continue
            dependency_nodes = [by_id[edge.from_node_id] for edge in edges if edge.to_node_id == node.id]
            if any(dep.status != "SUCCEEDED" for dep in dependency_nodes):
                raise AgentRuntimeError("dependency_not_ready")
            task_input = self._compose_task_input(plan, node, dependency_nodes)
            try:
                task = await self.runtime.create_task(
                    channel_id=channel.id,
                    agent_key=node.agent_key,
                    task_type=node.task_type,
                    action_type=node.action_type,
                    input_data=task_input,
                    budget_usd=node.estimated_cost_usd,
                    dependencies=dep_tasks[node.id],
                    idempotency_key=f"plan:{plan.id}:{node.node_key}:v{plan.plan_version}",
                    confidence=node.confidence,
                    requested_mode="auto",
                    plan_node_id=node.id,
                    project_id=plan.project_id,
                )
            except AgentRuntimeError:
                raise
            node.task_id = task.id
            await self.runtime._sync_plan_node(task)
            created.append(node)
            await self._event(plan, "NODE_MATERIALIZED", node_key=node.node_key, payload={"task_id": str(task.id), "dependency_task_ids": list(map(str, dep_tasks[node.id]))})
        await self._refresh_plan_status(plan)
        return created

    async def replan(
        self,
        plan: AgentPlan,
        *,
        failed_node_key: str,
        reason: str,
        preferred_agent: str | None = None,
    ) -> AgentPlan:
        if not reason.strip():
            raise ValueError("Replan reason is required")
        node = await self.db.scalar(select(AgentPlanNode).where(AgentPlanNode.plan_id == plan.id, AgentPlanNode.node_key == failed_node_key).with_for_update())
        if not node:
            raise ValueError("Plan node not found")
        if node.status != "FAILED":
            raise ValueError("Only failed nodes can be replanned")
        if node.retry_count >= self.settings.planner_max_retries:
            raise ValueError("Maximum node retry count reached")

        if preferred_agent:
            agent = await self.db.scalar(
                select(AgentDefinition).where(
                    AgentDefinition.channel_id == plan.channel_id,
                    AgentDefinition.agent_key == preferred_agent,
                    AgentDefinition.enabled.is_(True),
                )
            )
            if not agent or node.requested_capability not in (agent.capabilities or []):
                raise ValueError("Preferred agent does not provide the node capability")
            node.agent_key = preferred_agent

        channel = await self.db.get(Channel, plan.channel_id)
        gov = await self.governance.evaluate_action(
            channel=channel,
            action_type=node.action_type,
            estimated_cost_usd=node.estimated_cost_usd,
            confidence=node.confidence,
            requested_mode="auto",
        )
        node.retry_count += 1
        node.task_id = None
        node.risk_tier = gov["risk_tier"]
        node.governance_mode = gov["effective_mode"]
        node.governance_policy_version = gov["policy_version"]
        node.requires_approval = gov["requires_human_approval"]
        node.status = "BLOCKED" if not gov["allowed"] else ("PENDING_APPROVAL" if gov["effective_mode"] == "approve" else "PLANNED")
        node.rationale = f"Replanned attempt {node.retry_count}: {reason}. " + " ".join(gov["reasons"])
        plan.plan_version += 1
        plan.replan_count += 1
        plan.status = "BLOCKED" if node.status == "BLOCKED" else ("AWAITING_APPROVAL" if node.status == "PENDING_APPROVAL" else "PLANNED")
        plan.rationale = list(plan.rationale or []) + [f"Replanned node '{failed_node_key}' after: {reason}"]
        await self._event(plan, "NODE_REPLANNED", node_key=node.node_key, payload={"retry_count": node.retry_count, "reason": reason, "agent_key": node.agent_key})
        await self.db.flush()
        return plan

    async def _refresh_plan_status(self, plan: AgentPlan) -> None:
        nodes = (await self.db.execute(select(AgentPlanNode).where(AgentPlanNode.plan_id == plan.id))).scalars().all()
        if not nodes:
            plan.status = "DRAFT"
            return
        if any(n.status == "BLOCKED" for n in nodes):
            plan.status = "BLOCKED"
        elif all(n.status == "SUCCEEDED" for n in nodes):
            plan.status = "COMPLETED"
        elif any(n.status == "PENDING_APPROVAL" for n in nodes):
            plan.status = "AWAITING_APPROVAL"
        elif any(n.status in {"RUNNING", "READY", "PLANNED"} for n in nodes):
            plan.status = "RUNNING"
        elif any(n.status == "FAILED" for n in nodes):
            plan.status = "FAILED"
        else:
            plan.status = "PLANNED"

    async def _event(self, plan, event_type: str, node_key: str | None = None, payload: dict | None = None):
        self.db.add(AgentPlanEvent(
            organization_id=plan.organization_id,
            channel_id=plan.channel_id,
            plan_id=plan.id,
            plan_version=plan.plan_version,
            event_type=event_type,
            node_key=node_key,
            payload=payload or {},
        ))
        await self.db.flush()

    async def get_graph(self, plan: AgentPlan) -> dict[str, Any]:
        await self._sync_from_tasks(plan)
        nodes = list((await self.db.execute(select(AgentPlanNode).where(AgentPlanNode.plan_id == plan.id).order_by(AgentPlanNode.created_at))).scalars().all())
        edges = list((await self.db.execute(select(AgentPlanEdge).where(AgentPlanEdge.plan_id == plan.id))).scalars().all())
        return {
            "plan": self._plan_json(plan),
            "nodes": [self._node_json(n) for n in nodes],
            "edges": [{"from_node_id": str(e.from_node_id), "to_node_id": str(e.to_node_id)} for e in edges],
        }

    @staticmethod
    def _plan_json(p):
        return {
            "id": str(p.id), "channel_id": str(p.channel_id), "project_id": str(p.project_id) if p.project_id else None,
            "status": p.status, "goal": p.goal, "plan_version": p.plan_version, "replan_count": p.replan_count,
            "budget_usd": p.budget_usd, "estimated_cost_usd": p.estimated_cost_usd, "confidence": p.confidence,
            "strategy": p.strategy or {}, "governance_snapshot": p.governance_snapshot or {}, "rationale": p.rationale or [],
        }

    @staticmethod
    def _node_json(n):
        return {
            "id": str(n.id), "node_key": n.node_key, "status": n.status,
            "requested_capability": n.requested_capability, "agent_key": n.agent_key, "task_type": n.task_type,
            "action_type": n.action_type, "estimated_cost_usd": n.estimated_cost_usd, "confidence": n.confidence,
            "retry_count": n.retry_count, "requires_approval": n.requires_approval, "governance_mode": n.governance_mode,
            "risk_tier": n.risk_tier, "governance_policy_version": n.governance_policy_version,
            "rationale": n.rationale, "task_id": str(n.task_id) if n.task_id else None,
        }

