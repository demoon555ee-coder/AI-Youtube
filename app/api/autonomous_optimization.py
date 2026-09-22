from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, permission_dependency
from app.db.session import get_db
from app.models import AutonomousOptimizationDecision, Channel, CreativeAnalysis, PerformanceAlert, VideoProject
from app.autonomous_optimization import AutonomousOptimizationService, serialize_decision

router = APIRouter(prefix="/api/v1/optimization", tags=["autonomous-optimization"])


class DecisionRequest(BaseModel):
    alert_id: UUID | None = None
    max_actions: int = Field(default=3, ge=0, le=12)



def _assert_access(channel: Channel, principal: Principal) -> None:
    if principal.is_dev_fallback:
        return
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return
    if channel.owner_id == principal.scope_key:
        return
    raise HTTPException(404, "Resource not found")


async def _load_project(project_id: UUID, db: AsyncSession, principal: Principal) -> tuple[VideoProject, Channel]:
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    return project, channel


@router.post("/projects/{project_id}/decide", status_code=201)
async def decide_project_optimization(
    project_id: UUID,
    payload: DecisionRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    project, channel = await _load_project(project_id, db, principal)
    alert = None
    if payload.alert_id:
        alert = await db.get(PerformanceAlert, payload.alert_id)
        if not alert or alert.channel_id != channel.id or alert.organization_id != channel.organization_id:
            raise HTTPException(400, "Invalid alert for project")
    else:
        alert = await db.scalar(
            select(PerformanceAlert)
            .where(PerformanceAlert.channel_id == channel.id, PerformanceAlert.youtube_video_id == (project.data or {}).get("youtube_video_id", ""))
            .order_by(PerformanceAlert.created_at.desc())
        )
    decision = await AutonomousOptimizationService(db).decide(project=project, channel=channel, alert=alert, max_actions=payload.max_actions)
    await db.commit()
    await db.refresh(decision)
    return serialize_decision(decision)


@router.post("/channels/{channel_id}/decide")
async def decide_channel_optimization(
    channel_id: UUID,
    project_id: UUID = Query(...),
    payload: DecisionRequest = DecisionRequest(),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    project, channel = await _load_project(project_id, db, principal)
    if channel.id != channel_id:
        raise HTTPException(400, "Project does not belong to channel")
    alert = await db.get(PerformanceAlert, payload.alert_id) if payload.alert_id else None
    if alert and (alert.channel_id != channel.id or alert.organization_id != channel.organization_id):
        raise HTTPException(400, "Invalid alert for channel")
    decision = await AutonomousOptimizationService(db).decide(project=project, channel=channel, alert=alert, max_actions=payload.max_actions)
    await db.commit()
    return serialize_decision(decision)


@router.get("/projects/{project_id}/decisions")
async def list_project_decisions(
    project_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    project, _ = await _load_project(project_id, db, principal)
    rows = await db.execute(
        select(AutonomousOptimizationDecision)
        .where(AutonomousOptimizationDecision.project_id == project.id)
        .order_by(AutonomousOptimizationDecision.created_at.desc())
        .limit(limit)
    )
    return {"project_id": str(project_id), "decisions": [serialize_decision(row) for row in rows.scalars().all()]}


@router.get("/channels/{channel_id}/decisions")
async def list_channel_decisions(
    channel_id: UUID,
    status: str | None = Query(default=None, max_length=30),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    channel = await db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    stmt = select(AutonomousOptimizationDecision).where(AutonomousOptimizationDecision.channel_id == channel_id)
    if status:
        stmt = stmt.where(AutonomousOptimizationDecision.status == status)
    rows = await db.execute(stmt.order_by(AutonomousOptimizationDecision.created_at.desc()).limit(limit))
    return {"channel_id": str(channel_id), "decisions": [serialize_decision(row) for row in rows.scalars().all()]}
