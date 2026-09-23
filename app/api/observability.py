from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import engine, SessionLocal
from app.db.session import get_db
from app.auth.authorization import enforce_request_authorization
from app.models import Channel, MediaGenerationJob, VideoProject, WorkerHeartbeat, WorkflowDeadLetter
from app.observability.provider_health import ProviderHealthService
from app.resilience.provider import ProviderReliabilityService
from app.observability.access import metrics_token_matches

router = APIRouter(prefix='/api/v1/observability', tags=['observability'])
logger = logging.getLogger("youtube_ai_platform")


@router.get('/providers')
async def provider_health():
    if not settings.provider_health_enabled:
        raise HTTPException(404, 'Provider health monitoring is disabled')
    return ProviderHealthService().payload()


@router.get('/workers')
async def worker_health(stale_after_seconds: int = Query(default=90, ge=5, le=3600)):
    cutoff = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
    async with SessionLocal() as db:
        q = await db.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()))
        rows = list(q.scalars().all())
    workers = []
    for row in rows:
        fresh = row.last_seen_at >= cutoff
        workers.append({
            'worker_id': row.worker_id,
            'role': row.role,
            'host': row.host,
            'status': row.status if fresh else 'STALE',
            'active_workflow_id': str(row.active_workflow_id) if row.active_workflow_id else None,
            'started_at': row.started_at,
            'last_seen_at': row.last_seen_at,
            'metadata': row.metadata_json or {},
        })
    return {'workers': workers, 'healthy': all(item['status'] != 'STALE' for item in workers) if workers else False}


async def database_ready() -> tuple[bool, str | None]:
    try:
        async def _ping() -> None:
            async with engine.connect() as conn:
                await conn.execute(text('SELECT 1'))
        await asyncio.wait_for(_ping(), timeout=settings.readiness_timeout_seconds)
        return True, None
    except Exception as exc:
        logger.exception("database readiness check failed", exc_info=exc)
        return False, 'database unavailable'


@router.get("/circuits")
async def provider_circuits(request: Request, principal = Depends(enforce_request_authorization), db: AsyncSession = Depends(get_db)):
    owner_id = principal.organization_id if principal else "local-user"
    service = ProviderReliabilityService(db)
    from app.portfolio.service import PortfolioService
    portfolio = await PortfolioService(db).ensure(owner_id)
    rows = await service.snapshot(portfolio.id)
    return {"circuits": [{"provider": r.provider, "service": r.service, "state": r.state, "failure_count": r.failure_count, "success_count": r.success_count, "next_probe_at": r.next_probe_at} for r in rows]}


@router.get("/workflow/dead-letters")
async def workflow_dead_letters(request: Request, principal = Depends(enforce_request_authorization), db: AsyncSession = Depends(get_db), limit: int = Query(default=100, ge=1, le=500)):
    q = select(WorkflowDeadLetter).join(VideoProject, VideoProject.id == WorkflowDeadLetter.project_id).join(Channel, Channel.id == VideoProject.channel_id)
    if principal and principal.organization_id is not None:
        q = q.where((Channel.organization_id == principal.organization_id) | ((Channel.organization_id.is_(None)) & (Channel.owner_id == principal.scope_key)))
    rows = (await db.execute(q.order_by(WorkflowDeadLetter.created_at.desc()).limit(limit))).scalars().all()
    return {"dead_letters": [{"id": str(r.id), "workflow_run_id": str(r.workflow_run_id), "project_id": str(r.project_id), "reason": r.reason, "attempts": r.attempts, "created_at": r.created_at, "resolved_at": r.resolved_at} for r in rows]}


@router.get("/media/jobs")
async def media_jobs(request: Request, principal = Depends(enforce_request_authorization), db: AsyncSession = Depends(get_db), status: str | None = None, limit: int = Query(default=100, ge=1, le=500)):
    q = select(MediaGenerationJob).order_by(MediaGenerationJob.created_at.desc()).limit(limit)
    if principal and principal.organization_id is not None:
        q = q.where(MediaGenerationJob.organization_id == principal.organization_id)
    if status:
        q = q.where(MediaGenerationJob.status == status)
    rows = (await db.execute(q)).scalars().all()
    return {"jobs": [{"id": str(r.id), "project_id": str(r.project_id), "provider": r.provider, "status": r.status, "attempts": r.attempts, "external_job_id": r.external_job_id, "created_at": r.created_at, "completed_at": r.completed_at, "error": r.error_message} for r in rows]}
