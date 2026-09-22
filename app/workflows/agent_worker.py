from __future__ import annotations

import socket
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.factory import build_agent
from app.config import settings
from app.models import AgentTask, Channel, VideoProject
from app.observability import metrics
from app.runtime.service import AgentRuntimeError, AgentRuntimeService


class AgentTaskWorker:
    """Executes durable AgentTask records through the governed Runtime lifecycle."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.worker_id = f"{socket.gethostname()}:agent:{uuid.uuid4().hex[:8]}"
        self.poll_seconds = max(0.1, float(settings.workflow_poll_seconds))
        self.lease_seconds = max(30, int(settings.workflow_lease_seconds))

    async def run_forever(self) -> None:
        while True:
            did_work = await self.run_once()
            if not did_work:
                import asyncio
                await asyncio.sleep(self.poll_seconds)

    async def run_once(self) -> bool:
        async with self.session_factory() as db:
            task = await self._next_task(db)
            if task is None:
                return False
            runtime = AgentRuntimeService(db)
            try:
                lease = await runtime.acquire_lease(
                    task_id=task.id,
                    agent_key=task.agent_key,
                    ttl_seconds=self.lease_seconds,
                )
                await db.commit()
            except AgentRuntimeError as exc:
                await db.rollback()
                if str(exc) in {"task_not_ready", "approval_required", "governance_blocked", "agent_concurrency_limit"}:
                    return True
                metrics.inc("agent_tasks_failed_total", labels={"agent": task.agent_key, "reason": str(exc)})
                return True

        metrics.inc("agent_tasks_claimed_total", labels={"agent": task.agent_key})
        try:
            result = await self._execute_task(task, lease.lease_token)
        except Exception as exc:
            async with self.session_factory() as db:
                runtime = AgentRuntimeService(db)
                current = await db.get(AgentTask, task.id)
                if current is not None:
                    try:
                        await runtime.fail(task_id=task.id, lease_token=lease.lease_token, error=str(exc))
                        await db.commit()
                    except AgentRuntimeError:
                        await db.rollback()
            metrics.inc("agent_tasks_failed_total", labels={"agent": task.agent_key, "reason": type(exc).__name__})
            return True

        async with self.session_factory() as db:
            runtime = AgentRuntimeService(db)
            try:
                current = await db.get(AgentTask, task.id)
                if current is None:
                    return True
                actual_cost = self._actual_cost(result, current.requested_budget_usd)
                await runtime.complete(
                    task_id=task.id,
                    lease_token=lease.lease_token,
                    output_data=result,
                    actual_cost_usd=actual_cost,
                )
                await db.commit()
            except AgentRuntimeError as exc:
                await db.rollback()
                metrics.inc("agent_tasks_failed_total", labels={"agent": task.agent_key, "reason": str(exc)})
                return True
        metrics.inc("agent_tasks_completed_total", labels={"agent": task.agent_key})
        return True

    async def _next_task(self, db: AsyncSession) -> AgentTask | None:
        query = (
            select(AgentTask)
            .where(AgentTask.status == "PENDING", AgentTask.governance_approved.is_(True))
            .order_by(AgentTask.priority.desc(), AgentTask.created_at.asc())
            .limit(20)
        )
        tasks = (await db.execute(query)).scalars().all()
        runtime = AgentRuntimeService(db)
        for task in tasks:
            try:
                if await runtime.readiness(task):
                    return task
            except Exception:
                continue
        return None

    async def _execute_task(self, task: AgentTask, lease_token: str) -> dict:
        # Use a fresh session while the provider runs so the Runtime lease transaction
        # remains committed and visible to other workers.
        async with self.session_factory() as db:
            current = await db.get(AgentTask, task.id)
            if current is None:
                raise AgentRuntimeError("task_not_found")
            channel = await db.get(Channel, current.channel_id)
            if channel is None:
                raise AgentRuntimeError("channel_not_found")
            project = await db.get(VideoProject, current.project_id) if current.project_id else None
            input_data = dict(current.input_data or {})
            routing_plan = dict((project.data or {}).get("routing_plan") or {}) if project else {}
            routing_plan.update(dict(input_data.get("routing_plan") or {}))
            route_meta = dict(routing_plan.get(current.agent_key) or {})
            config = dict(route_meta.get("config") or {})
            provider = route_meta.get("provider")

            if current.agent_key == "publisher":
                config["_db"] = db
                input_data.setdefault("channel_id", str(channel.id))
                input_data.setdefault("project_id", str(current.project_id) if current.project_id else "")
                if project:
                    pdata = project.data or {}
                    script = pdata.get("script") or {}
                    research = pdata.get("research") or {}
                    input_data.setdefault("title", script.get("title") or pdata.get("title") or project.topic)
                    input_data.setdefault("description", script.get("description") or pdata.get("description") or "")
                    input_data.setdefault("tags", research.get("keywords") or [])
                    input_data.setdefault("privacy_status", pdata.get("publication", {}).get("privacy_status") or "private")
            elif current.agent_key == "research":
                llm_route = dict(routing_plan.get("research_llm") or {})
                config["llm_provider"] = llm_route.get("provider")
                config["llm_config"] = llm_route.get("config") or {}
            elif current.agent_key == "production":
                video_route = dict(routing_plan.get("production_video") or {})
                config.update({
                    "image_provider": provider,
                    "image_config": dict(route_meta.get("config") or {}),
                    "video_provider": video_route.get("provider"),
                    "video_config": dict(video_route.get("config") or {}),
                    "_db": db,
                    "_organization_id": channel.organization_id,
                    "_channel_id": channel.id,
                })

            agent = build_agent(current.agent_key, provider=provider, config=config)
            if agent is None:
                raise AgentRuntimeError(f"no_agent_implementation:{current.agent_key}")

            result = await agent.run(input_data)
            return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _actual_cost(result: dict, requested_budget: float) -> Decimal:
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        raw = result.get("actual_cost_usd", usage.get("actual_cost_usd", 0))
        try:
            value = Decimal(str(raw))
        except Exception:
            value = Decimal("0")
        return max(Decimal("0"), min(Decimal(str(requested_budget)), value))
