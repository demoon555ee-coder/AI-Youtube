from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db, SessionLocal
from app.auth.security import Principal, get_current_principal, permission_dependency
from app.models import Channel, PostPublishMonitor, PerformanceAlert, Publication, VideoProject, ContentVersion
from app.postpublish.service import PostPublishMonitorService
from app.evolution.service import ContentEvolutionService, build_evolution_plan
from app.workflows.engine import WorkflowEngine

router = APIRouter(prefix="/api/v1/post-publish", tags=["post-publish"])

class RevisionFromAlertRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)
    auto_run: bool = True


class MonitorRequest(BaseModel):
    video_id: str = Field(min_length=3, max_length=128)
    project_id: str | None = None
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    baseline_days: int = Field(default=28, ge=7, le=90)
    anomaly_threshold_pct: float = Field(default=20.0, ge=5, le=80)
    auto_correct: bool = False

@router.post("/channels/{channel_id}/monitors")
async def create_monitor(channel_id: UUID, payload: MonitorRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    portfolio_id = None
    try:
        from app.portfolio.service import PortfolioService
        portfolio_id = (await PortfolioService(db).ensure(principal.scope_key)).id
    except Exception:
        pass
    project_id = UUID(payload.project_id) if payload.project_id else None
    if project_id:
        project = await db.get(VideoProject, project_id)
        if not project or project.channel_id != channel.id:
            raise HTTPException(404, "Project not found")
    row = await PostPublishMonitorService(db).create(
        organization_id=principal.organization_id,
        portfolio_id=portfolio_id,
        channel_id=channel.id,
        video_id=payload.video_id,
        project_id=project_id,
        interval_minutes=payload.interval_minutes,
        baseline_days=payload.baseline_days,
        anomaly_threshold_pct=payload.anomaly_threshold_pct,
        auto_correct=payload.auto_correct,
    )
    return {"id": str(row.id), "channel_id": str(row.channel_id), "video_id": row.youtube_video_id, "enabled": row.enabled, "next_check_at": row.next_check_at}

@router.get("/channels/{channel_id}/monitors")
async def list_monitors(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    q = await db.execute(select(PostPublishMonitor).where(PostPublishMonitor.channel_id == channel_id).order_by(PostPublishMonitor.created_at.desc()))
    return {"channel_id": str(channel_id), "monitors": [{"id": str(x.id), "video_id": x.youtube_video_id, "enabled": x.enabled, "status": x.last_status, "next_check_at": x.next_check_at, "last_checked_at": x.last_checked_at, "auto_correct": x.auto_correct} for x in q.scalars().all()]}

@router.post("/monitors/{monitor_id}/run")
async def run_monitor(monitor_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return await PostPublishMonitorService(db).check_one(monitor_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(502, "Post-publish monitor failed") from exc

@router.get("/channels/{channel_id}/alerts")
async def list_alerts(channel_id: UUID, status: str | None = Query(default=None), db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    q = select(PerformanceAlert).where(PerformanceAlert.channel_id == channel_id).order_by(PerformanceAlert.created_at.desc()).limit(100)
    if status:
        q = q.where(PerformanceAlert.status == status)
    rows = await db.execute(q)
    return {"channel_id": str(channel_id), "alerts": [{"id": str(x.id), "video_id": x.youtube_video_id, "alert_type": x.alert_type, "severity": x.severity, "metric": x.metric, "current_value": x.current_value, "baseline_value": x.baseline_value, "delta_pct": x.delta_pct, "status": x.status, "evidence": x.evidence, "remediation": x.remediation, "created_at": x.created_at, "resolved_at": x.resolved_at} for x in rows.scalars().all()]}

@router.post("/alerts/{alert_id}/create-revision", status_code=201)
async def create_revision_from_alert(
    alert_id: UUID,
    payload: RevisionFromAlertRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    alert = await db.get(PerformanceAlert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    monitor = await db.get(PostPublishMonitor, alert.monitor_id)
    if not monitor or monitor.channel_id != alert.channel_id:
        raise HTTPException(409, "Alert monitor is invalid")
    if not monitor.project_id:
        raise HTTPException(409, "Alert is not linked to a source project")
    source = await db.get(VideoProject, monitor.project_id)
    channel = await db.get(Channel, alert.channel_id)
    publication = await db.scalar(select(Publication).where(Publication.project_id == monitor.project_id, Publication.youtube_video_id == alert.youtube_video_id))
    if not source or not channel:
        raise HTTPException(404, "Source project not found")
    if not publication:
        raise HTTPException(409, "Alert is not linked to a published source project")
    if principal.organization_id is not None and channel.organization_id != principal.organization_id and not principal.is_dev_fallback:
        raise HTTPException(404, "Alert not found")
    existing = await db.scalar(select(ContentVersion).where(ContentVersion.trigger_alert_id == alert.id))
    if existing:
        return {
            "version_id": str(existing.id),
            "project_id": str(existing.project_id),
            "revision_number": existing.revision_number,
            "status": existing.status,
            "created": False,
        }
    plan = build_evolution_plan(
        alert_type=alert.alert_type,
        metric=alert.metric,
        delta_pct=alert.delta_pct,
        evidence=alert.evidence,
    )
    revision, version = await ContentEvolutionService(db).create_revision(
        source_project=source,
        trigger_type="post_publish_anomaly",
        reason=payload.reason or f"Post-publish anomaly: {alert.metric} {alert.delta_pct:.1f}% vs baseline",
        change_plan=plan,
        metrics_snapshot={
            "metric": alert.metric,
            "current_value": alert.current_value,
            "baseline_value": alert.baseline_value,
            "delta_pct": alert.delta_pct,
            "evidence": alert.evidence,
        },
        trigger_alert_id=alert.id,
    )
    await db.commit()
    workflow_id = None
    if payload.auto_run:
        try:
            run = await WorkflowEngine(SessionLocal).create_or_get(revision.id, f"evolution-alert:{alert.id}")
            workflow_id = str(run.id)
        except Exception:
            workflow_id = None
    return {
        "version_id": str(version.id),
        "project_id": str(revision.id),
        "revision_number": version.revision_number,
        "parent_project_id": str(source.id),
        "workflow_id": workflow_id,
        "status": revision.status,
        "created": True,
    }


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    row = await db.get(PerformanceAlert, alert_id)
    if not row:
        raise HTTPException(404, "Alert not found")
    row.status = "ACKNOWLEDGED"
    await db.commit()
    return {"id": str(row.id), "status": row.status}
