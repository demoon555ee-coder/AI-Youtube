import asyncio
import contextlib
import socket
import uuid
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.session import SessionLocal, engine
from app.models.base import Base
from app.db.migrations import apply_migrations
from app import models  # noqa: F401
from app.models import VideoProject, WorkflowEvent, WorkflowRun, WorkflowStep, WorkerHeartbeat
from app.billing.service import BillingService
from app.services.orchestrator import Orchestrator
from app.autopilot.service import AutopilotService
from app.research.scheduler import ResearchSchedulerService
from app.privacy.service import process_deletion_request, run_retention_cleanup
from app.models import PrivacyRequest
from app.media.recovery import MediaRecoveryService
from app.postpublish.service import PostPublishMonitorService
from app.observability import metrics, tracing
from app.workflows.agent_worker import AgentTaskWorker

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Return naive UTC for compatibility with existing TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _billing_webhook_loop() -> None:
    while True:
        async with SessionLocal() as db:
            try:
                await BillingService(db).process_pending_webhooks(limit=5)
            except Exception:
                await db.rollback()
        await asyncio.sleep(max(1.0, settings.workflow_poll_seconds))


async def _autopilot_loop() -> None:
    while True:
        async with SessionLocal() as db:
            try:
                await AutopilotService(db).process_due_items()
            except Exception:
                await db.rollback()
        await asyncio.sleep(15)


async def _research_loop() -> None:
    if not settings.research_scheduler_enabled:
        return
    while True:
        async with SessionLocal() as db:
            try:
                await ResearchSchedulerService(db, lease_minutes=settings.research_scheduler_lease_minutes).process_due(limit=settings.research_scheduler_batch_size)
            except Exception:
                await db.rollback()
        await asyncio.sleep(max(5.0, settings.research_scheduler_poll_seconds))




async def _media_recovery_loop() -> None:
    if not settings.media_recovery_enabled:
        return
    while True:
        async with SessionLocal() as db:
            try:
                await MediaRecoveryService(db).process_due()
            except Exception:
                await db.rollback()
        await asyncio.sleep(max(2.0, settings.media_recovery_poll_seconds))


async def _postpublish_loop() -> None:
    if not getattr(settings, "postpublish_enabled", True):
        return
    while True:
        async with SessionLocal() as db:
            try:
                await PostPublishMonitorService(db).process_due(limit=5)
            except Exception:
                await db.rollback()
        await asyncio.sleep(max(15.0, getattr(settings, "postpublish_poll_seconds", 60.0)))


async def _privacy_maintenance_loop() -> None:
    while True:
        async with SessionLocal() as db:
            try:
                pending = await db.execute(
                    select(PrivacyRequest.id)
                    .where(PrivacyRequest.status == "REQUESTED", PrivacyRequest.request_type == "ERASURE")
                    .order_by(PrivacyRequest.created_at.asc())
                    .limit(10)
                    .with_for_update(skip_locked=True)
                )
                for request_id in pending.scalars().all():
                    await process_deletion_request(db, request_id)
                await run_retention_cleanup(db)
                await db.commit()
            except Exception:
                await db.rollback()
        await asyncio.sleep(max(30, settings.maintenance_poll_seconds))


# Re-export the real class while adding heartbeat/metrics through a subclass.
from app.workflows.engine import WorkflowWorker as EngineWorkflowWorker


class ObservableWorkflowWorker(EngineWorkflowWorker):
    async def heartbeat(self, *, status: str, active_workflow_id: uuid.UUID | None = None) -> None:
        now = _utcnow()
        async with self.session_factory() as db:
            row_q = await db.execute(select(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == self.worker_id).with_for_update())
            row = row_q.scalar_one_or_none()
            if row is None:
                row = WorkerHeartbeat(
                    worker_id=self.worker_id,
                    role='workflow',
                    host=socket.gethostname(),
                    status=status,
                    active_workflow_id=active_workflow_id,
                    started_at=now,
                    last_seen_at=now,
                    metadata_json={'version': settings.app_version},
                )
                db.add(row)
            else:
                row.status = status
                row.active_workflow_id = active_workflow_id
                row.last_seen_at = now
            await db.commit()

    async def run_once(self) -> bool:
        workflow = await self._claim()
        if not workflow:
            return False
        logger.info("workflow claimed id=%s project_id=%s attempt=%s", workflow.id, workflow.project_id, workflow.attempt)
        await self.heartbeat(status='RUNNING', active_workflow_id=workflow.id)
        metrics.inc('workflow_runs_claimed_total', labels={'status': workflow.status})
        heartbeat = asyncio.create_task(self._heartbeat(workflow.id))
        started = asyncio.get_running_loop().time()
        try:
            with tracing.span('workflow.run'):
                async with self.session_factory() as db:
                    project = await db.get(VideoProject, workflow.project_id)
                    if not project:
                        await self._finish(workflow.id, 'FAILED', 'Project not found')
                        return True
                try:
                    async with self.session_factory() as db:
                        project = await db.get(VideoProject, workflow.project_id)
                        if project:
                            await self._event_for_db(db, workflow.id, project.id, 'workflow.started', {'worker_id': self.worker_id, 'attempt': workflow.attempt})
                            await db.commit()
                    async with self.session_factory() as db:
                        await Orchestrator(db).run_project(str(workflow.project_id), workflow_id=str(workflow.id))
                        from app.services.autopilot_state import sync_plan_item_after_workflow
                        await sync_plan_item_after_workflow(db, workflow.project_id, 'READY_TO_PUBLISH')
                        await db.commit()
                        from app.services.autopilot_publisher import auto_publish_if_due
                        await auto_publish_if_due(db, workflow.project_id)
                    await self._finish(workflow.id, 'COMPLETED', None)
                    metrics.inc('workflow_runs_completed_total', labels={'status': 'COMPLETED'})
                except Exception as exc:
                    logger.exception("workflow execution failed id=%s project_id=%s", workflow.id, workflow.project_id)
                    async with self.session_factory() as db:
                        current = await db.get(WorkflowRun, workflow.id)
                    if current and current.status == 'CANCELLED':
                        await self.heartbeat(status='IDLE')
                        return True
                    await self._finish(workflow.id, 'FAILED', str(exc))
        finally:
            duration = asyncio.get_running_loop().time() - started
            metrics.observe('workflow_run_duration_seconds', duration, labels={'status': 'finished'})
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            await self.heartbeat(status='IDLE')
        return True

    async def _heartbeat(self, workflow_id: uuid.UUID) -> None:
        interval = max(1, self.lease_seconds // 3)
        while True:
            await asyncio.sleep(interval)
            async with self.session_factory() as db:
                run = await db.get(WorkflowRun, workflow_id)
                if not run or run.status != 'RUNNING' or run.worker_id != self.worker_id:
                    return
                run.lease_until = _utcnow() + timedelta(seconds=self.lease_seconds)
                run.updated_at = _utcnow()
                await db.commit()
            await self.heartbeat(status='RUNNING', active_workflow_id=workflow_id)


async def main() -> None:
    if settings.auto_migrate:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await apply_migrations(engine)
    worker = ObservableWorkflowWorker(SessionLocal)
    agent_worker = AgentTaskWorker(SessionLocal)
    await worker.heartbeat(status='STARTING')
    billing_task = asyncio.create_task(_billing_webhook_loop())
    agent_task_worker = asyncio.create_task(agent_worker.run_forever())
    autopilot_task = asyncio.create_task(_autopilot_loop())
    research_task = asyncio.create_task(_research_loop())
    privacy_task = asyncio.create_task(_privacy_maintenance_loop())
    media_recovery_task = asyncio.create_task(_media_recovery_loop())
    postpublish_task = asyncio.create_task(_postpublish_loop())
    try:
        await worker.run_forever()
    except Exception:
        logger.exception("workflow worker loop crashed")
        raise
    finally:
        billing_task.cancel()
        agent_task_worker.cancel()
        autopilot_task.cancel()
        research_task.cancel()
        privacy_task.cancel()
        media_recovery_task.cancel()
        postpublish_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await billing_task
        with contextlib.suppress(asyncio.CancelledError):
            await agent_task_worker
        with contextlib.suppress(asyncio.CancelledError):
            await autopilot_task
        with contextlib.suppress(asyncio.CancelledError):
            await research_task
        with contextlib.suppress(asyncio.CancelledError):
            await privacy_task
        with contextlib.suppress(asyncio.CancelledError):
            await media_recovery_task
        with contextlib.suppress(asyncio.CancelledError):
            await postpublish_task
        await worker.heartbeat(status='STOPPED')
        worker.stop()
        await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
