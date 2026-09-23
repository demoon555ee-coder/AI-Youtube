from __future__ import annotations

import asyncio
import contextlib
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models import VideoProject, WorkflowEvent, WorkflowRun, WorkflowStep, WorkflowDeadLetter
from app.services.orchestrator import Orchestrator

WORKFLOW_STEPS = [
    ("research", "RESEARCHING"),
    ("script", "SCRIPTING"),
    ("storyboard", "STORYBOARDING"),
    ("scene_director", "DIRECTING_SCENES"),
    ("production", "GENERATING_ASSETS"),
    ("editor", "EDITING"),
    ("thumbnail", "GENERATING_THUMBNAIL"),
    ("qa", "QA"),
]
ACTIVE_STATUSES = {"QUEUED", "RUNNING"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorkflowEngine:
    """Durable DB-backed workflow queue.

    PostgreSQL row locking + leases make the queue safe across multiple API/worker
    processes without requiring Redis or a separate workflow service for the MVP.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_or_get(self, project_id: uuid.UUID, idempotency_key: str) -> WorkflowRun:
        async with self.session_factory() as db:
            project = await db.get(VideoProject, project_id, with_for_update=True)
            if not project:
                raise ValueError("Project not found")

            existing_q = await db.execute(select(WorkflowRun).where(WorkflowRun.idempotency_key == idempotency_key))
            existing = existing_q.scalar_one_or_none()
            if existing:
                if existing.project_id != project_id:
                    raise ValueError("Idempotency key is already used by another project")
                return existing

            active_q = await db.execute(
                select(WorkflowRun)
                .where(WorkflowRun.project_id == project_id, WorkflowRun.status.in_(ACTIVE_STATUSES))
                .order_by(WorkflowRun.created_at.desc())
                .limit(1)
            )
            active = active_q.scalar_one_or_none()
            if active:
                return active

            run = WorkflowRun(project_id=project_id, idempotency_key=idempotency_key)
            db.add(run)
            await db.flush()
            for order, (step_key, _) in enumerate(WORKFLOW_STEPS):
                db.add(WorkflowStep(workflow_run_id=run.id, step_key=step_key, step_order=order))
            await self._event(db, run, "workflow.queued", {"attempt": run.attempt})
            project.status = "QUEUED"
            await db.commit()
            await db.refresh(run)
            return run

    async def retry(self, project_id: uuid.UUID) -> WorkflowRun:
        async with self.session_factory() as db:
            project = await db.get(VideoProject, project_id, with_for_update=True)
            if not project:
                raise ValueError("Project not found")
            active_q = await db.execute(
                select(WorkflowRun).where(WorkflowRun.project_id == project_id, WorkflowRun.status.in_(ACTIVE_STATUSES)).limit(1)
            )
            if active_q.scalar_one_or_none():
                raise ValueError("Project already has an active workflow")
            last_q = await db.execute(
                select(WorkflowRun).where(WorkflowRun.project_id == project_id).order_by(WorkflowRun.attempt.desc()).limit(1)
            )
            last = last_q.scalar_one_or_none()
            attempt = (last.attempt + 1) if last else 1
            run = WorkflowRun(project_id=project_id, idempotency_key=f"retry:{project_id}:{attempt}", attempt=attempt)
            db.add(run)
            await db.flush()
            previous_steps: dict[str, WorkflowStep] = {}
            if last:
                prev_q = await db.execute(
                    select(WorkflowStep).where(WorkflowStep.workflow_run_id == last.id)
                )
                previous_steps = {step.step_key: step for step in prev_q.scalars().all()}

            for order, (step_key, _) in enumerate(WORKFLOW_STEPS):
                previous = previous_steps.get(step_key)
                if previous and previous.status == "COMPLETED":
                    db.add(WorkflowStep(
                        workflow_run_id=run.id, step_key=step_key, step_order=order,
                        status="COMPLETED", output_data=previous.output_data or {},
                    ))
                else:
                    db.add(WorkflowStep(workflow_run_id=run.id, step_key=step_key, step_order=order))
            project.status = "QUEUED"
            await self._event(db, run, "workflow.queued", {"attempt": attempt, "retry": True, "resume_from": next((key for key, _ in WORKFLOW_STEPS if not previous_steps.get(key) or previous_steps[key].status != "COMPLETED"), "completed")})
            await db.commit()
            await db.refresh(run)
            return run

    async def get_run(self, workflow_id: uuid.UUID) -> WorkflowRun | None:
        async with self.session_factory() as db:
            return await db.get(WorkflowRun, workflow_id)

    async def list_steps(self, workflow_id: uuid.UUID) -> list[WorkflowStep]:
        async with self.session_factory() as db:
            q = await db.execute(select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow_id).order_by(WorkflowStep.step_order))
            return list(q.scalars().all())

    async def _event(self, db: AsyncSession, run: WorkflowRun, event_type: str, payload: dict) -> None:
        db.add(WorkflowEvent(workflow_run_id=run.id, project_id=run.project_id, event_type=event_type, payload=payload))


class WorkflowWorker:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self.worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self.poll_seconds = settings.workflow_poll_seconds
        self.lease_seconds = settings.workflow_lease_seconds
        self._stop = asyncio.Event()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            did_work = await self.run_once()
            if not did_work:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
                except asyncio.TimeoutError:
                    pass

    def stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> bool:
        workflow = await self._claim()
        if not workflow:
            return False

        heartbeat = asyncio.create_task(self._heartbeat(workflow.id))
        try:
            async with self.session_factory() as db:
                project = await db.get(VideoProject, workflow.project_id)
                if not project:
                    await self._finish(workflow.id, "FAILED", "Project not found")
                    return True
            try:
                async with self.session_factory() as db:
                    project = await db.get(VideoProject, workflow.project_id)
                    if project:
                        await self._event_for_db(db, workflow.id, project.id, "workflow.started", {"worker_id": self.worker_id, "attempt": workflow.attempt})
                        await db.commit()
                async with self.session_factory() as db:
                    await Orchestrator(db).run_project(str(workflow.project_id), workflow_id=str(workflow.id))
                    # Keep post-production state changes in the same live session.
                    from app.services.autopilot_state import sync_plan_item_after_workflow
                    await sync_plan_item_after_workflow(db, workflow.project_id, "READY_TO_PUBLISH")
                    await db.commit()
                    # Autopilot can publish privately with a future publishAt when OAuth is available.
                    from app.services.autopilot_publisher import auto_publish_if_due
                    await auto_publish_if_due(db, workflow.project_id)
                    from app.execution.controller import AutonomousExecutionController
                    await AutonomousExecutionController(db).reconcile_workflow(workflow.id, success=True, result={"project_status":"READY_TO_PUBLISH"})
                await self._finish(workflow.id, "COMPLETED", None)
            except Exception as exc:
                async with self.session_factory() as db:
                    current = await db.get(WorkflowRun, workflow.id)
                if current and current.status == "CANCELLED":
                    return True
                async with self.session_factory() as db:
                    from app.execution.controller import AutonomousExecutionController
                    await AutonomousExecutionController(db).reconcile_workflow(workflow.id, success=False, result={"error":str(exc)})
                    await db.commit()
                await self._finish(workflow.id, "FAILED", str(exc))
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        return True

    async def _claim(self) -> WorkflowRun | None:
        now = utcnow()
        async with self.session_factory() as db:
            q = await db.execute(
                select(WorkflowRun)
                .where(
                    (WorkflowRun.next_run_at.is_(None) | (WorkflowRun.next_run_at <= now)),
                    or_(
                        WorkflowRun.status == "QUEUED",
                        (WorkflowRun.status == "RUNNING") & (WorkflowRun.lease_until < now),
                    ),
                )
                .order_by(WorkflowRun.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            run = q.scalar_one_or_none()
            if not run:
                return None
            run.status = "RUNNING"
            run.worker_id = self.worker_id
            run.started_at = run.started_at or now
            run.lease_until = now + timedelta(seconds=self.lease_seconds)
            run.next_run_at = None
            run.updated_at = now
            await db.commit()
            await db.refresh(run)
            return run

    async def _heartbeat(self, workflow_id: uuid.UUID) -> None:
        interval = max(1, self.lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            async with self.session_factory() as db:
                run = await db.get(WorkflowRun, workflow_id)
                if not run or run.status != "RUNNING" or run.worker_id != self.worker_id:
                    return
                run.lease_until = utcnow() + timedelta(seconds=self.lease_seconds)
                run.updated_at = utcnow()
                await db.commit()

    async def _finish(self, workflow_id: uuid.UUID, status: str, error: str | None) -> None:
        async with self.session_factory() as db:
            run = await db.get(WorkflowRun, workflow_id)
            if not run:
                return

            project = await db.get(VideoProject, run.project_id)
            if status == "FAILED" and run.status != "CANCELLED":
                step_q = await db.execute(
                    select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow_id).order_by(WorkflowStep.step_order)
                )
                steps = list(step_q.scalars().all())
                retryable = next((step for step in steps if step.status == "PENDING" and step.attempts < step.max_attempts), None)
                if retryable:
                    delay = min(300, 2 ** max(retryable.attempts - 1, 0))
                    run.status = "QUEUED"
                    run.next_run_at = utcnow() + timedelta(seconds=delay)
                    run.last_error = error
                    run.lease_until = None
                    run.updated_at = utcnow()
                    if project:
                        project.status = "QUEUED"
                        await self._event_for_db(db, run.id, project.id, "workflow.retry_scheduled", {"step": retryable.step_key, "delay_seconds": delay, "attempt": retryable.attempts})
                    await db.commit()
                    return

            run.status = status
            run.last_error = error
            if status == "FAILED" and settings.workflow_dead_letter_enabled:
                existing_dl = await db.scalar(select(WorkflowDeadLetter).where(WorkflowDeadLetter.workflow_run_id == run.id))
                if existing_dl is None:
                    steps_for_dl = list((await db.execute(select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow_id))).scalars().all())
                    db.add(WorkflowDeadLetter(
                        workflow_run_id=run.id,
                        project_id=run.project_id,
                        reason=error or "workflow failed without retryable steps",
                        attempts=sum(step.attempts for step in steps_for_dl),
                        metadata_json={"status": status},
                    ))
            run.finished_at = utcnow()
            run.lease_until = None
            run.next_run_at = None
            run.updated_at = utcnow()
            if project and status == "FAILED":
                project.status = "FAILED"
                from app.services.autopilot_state import sync_plan_item_after_workflow
                await sync_plan_item_after_workflow(db, project.id, "FAILED")
            if project:
                await self._event_for_db(db, run.id, project.id, f"workflow.{status.lower()}", {"error": error} if error else {})
            await db.commit()

    async def _event_for_db(self, db: AsyncSession, workflow_id: uuid.UUID, project_id: uuid.UUID, event_type: str, payload: dict) -> None:
        db.add(WorkflowEvent(workflow_run_id=workflow_id, project_id=project_id, event_type=event_type, payload=payload))

