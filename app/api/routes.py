from pathlib import Path
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import SessionLocal, get_db
from app.models import (
    AnalyticsSnapshot,
    AgentRun,
    Channel,
    Publication,
    VideoProject,
    WorkflowRun,
    WorkflowStep,
)
from app.workflows.engine import WorkflowEngine
from app.auth.security import Principal, get_current_principal, require_roles, permission_dependency
from app.billing.service import BillingService

router = APIRouter(prefix="/api/v1", tags=["projects"])


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    niche: str | None = None
    language: str = Field(default="en", min_length=2, max_length=10)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)


class ProjectCreate(BaseModel):
    channel_id: UUID
    topic: str = Field(min_length=1, max_length=1000)


async def _get_owned_channel(
    channel_id: UUID,
    db: AsyncSession,
    principal: Principal,
) -> Channel:
    channel = await db.get(Channel, channel_id)
    if not channel or ((channel.organization_id is not None and channel.organization_id != principal.organization_id) or (channel.organization_id is None and channel.owner_id != principal.scope_key)):
        raise HTTPException(404, "Channel not found")
    return channel


async def _get_owned_project(
    project_id: UUID,
    db: AsyncSession,
    principal: Principal,
) -> VideoProject:
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await _get_owned_channel(project.channel_id, db, principal)
    return project


@router.post("/channels")
async def create_channel(payload: ChannelCreate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    owner_key = principal.scope_key
    if principal.organization_id is not None:
        entitlement = await BillingService(db).entitlement(principal.organization_id, "max_channels")
        current_count = await db.scalar(select(func.count(Channel.id)).where(Channel.organization_id == principal.organization_id))
        if entitlement["limit"] is not None and int(current_count or 0) >= int(entitlement["limit"]):
            raise HTTPException(status_code=402, detail="Channel limit reached for the current plan")
    channel = Channel(owner_id=owner_key, organization_id=principal.organization_id, name=payload.name, niche=payload.niche, language=payload.language, timezone=payload.timezone)
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return {"id": str(channel.id), "name": channel.name, "niche": channel.niche, "language": channel.language}


@router.get("/channels")
async def list_channels(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    q = await db.execute(select(Channel).where(Channel.owner_id == principal.scope_key).order_by(Channel.created_at.desc()))
    return {
        "channels": [
            {
                "id": str(channel.id),
                "name": channel.name,
                "niche": channel.niche,
                "language": channel.language,
                "youtube_channel_id": channel.youtube_channel_id,
            }
            for channel in q.scalars().all()
        ]
    }


@router.get("/channels/{channel_id}/dashboard")
async def channel_dashboard(channel_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _get_owned_channel(channel_id, db, principal)
    total_views = await db.scalar(select(func.coalesce(func.sum(AnalyticsSnapshot.views), 0)).where(AnalyticsSnapshot.channel_id == channel_id))
    total_watch = await db.scalar(select(func.coalesce(func.sum(AnalyticsSnapshot.watch_time_minutes), 0)).where(AnalyticsSnapshot.channel_id == channel_id))
    gained = await db.scalar(select(func.coalesce(func.sum(AnalyticsSnapshot.subscribers_gained), 0)).where(AnalyticsSnapshot.channel_id == channel_id))
    lost = await db.scalar(select(func.coalesce(func.sum(AnalyticsSnapshot.subscribers_lost), 0)).where(AnalyticsSnapshot.channel_id == channel_id))
    video_count = await db.scalar(select(func.count(VideoProject.id)).where(VideoProject.channel_id == channel_id))
    projects_q = await db.execute(select(VideoProject).where(VideoProject.channel_id == channel_id).order_by(VideoProject.updated_at.desc()).limit(10))
    projects = list(projects_q.scalars().all())
    return {
        "channel": {"id": str(channel.id), "name": channel.name, "niche": channel.niche, "language": channel.language, "timezone": channel.timezone, "youtube_channel_id": channel.youtube_channel_id},
        "metrics": {
            "views": int(total_views or 0),
            "watch_time_minutes": float(total_watch or 0),
            "subscribers_net": int((gained or 0) - (lost or 0)),
            "videos": int(video_count or 0),
        },
        "projects": [{"id": str(p.id), "topic": p.topic, "status": p.status, "title": (p.data or {}).get("title")} for p in projects],
    }


@router.get("/channels/{channel_id}/projects")
async def channel_projects(channel_id: UUID, limit: int = 50, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    channel = await _get_owned_channel(channel_id, db, principal)
    q = await db.execute(select(VideoProject).where(VideoProject.channel_id == channel_id).order_by(VideoProject.updated_at.desc()).limit(min(max(limit, 1), 100)))
    return {"channel_id": str(channel_id), "projects": [{"id": str(p.id), "topic": p.topic, "status": p.status, "data": p.data or {}} for p in q.scalars().all()]}


@router.post("/projects")
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("content:write"))):
    channel = await _get_owned_channel(payload.channel_id, db, principal)
    project = VideoProject(channel_id=channel.id, topic=payload.topic)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {"id": str(project.id), "status": project.status}


@router.post("/projects/{project_id}/run", status_code=202)
async def run_project(
    project_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles({"owner", "admin", "editor"})),
):
    project = await _get_owned_project(project_id, db, principal)
    if project.status in {"QUEUED", "RESEARCHING", "SCRIPTING", "STORYBOARDING", "GENERATING_ASSETS", "EDITING", "GENERATING_THUMBNAIL", "QA"}:
        q = await db.execute(select(WorkflowRun).where(WorkflowRun.project_id == project_id, WorkflowRun.status.in_({"QUEUED", "RUNNING"})).order_by(WorkflowRun.created_at.desc()).limit(1))
        run = q.scalar_one_or_none()
        return {"id": str(project.id), "workflow_id": str(run.id) if run else None, "status": project.status, "started": False, "message": "Project is already running"}
    if project.status == "READY_TO_PUBLISH":
        return {"id": str(project.id), "status": project.status, "started": False, "message": "Project is already ready to publish"}
    if project.status == "FAILED":
        raise HTTPException(409, "Project failed; use /retry to resume from the last successful checkpoint")
    key = (idempotency_key or f"run:{project_id}:{uuid.uuid4().hex}")[:255]
    try:
        run = await WorkflowEngine(SessionLocal).create_or_get(project.id, key)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": str(project.id), "workflow_id": str(run.id), "status": run.status, "started": True}


@router.post("/projects/{project_id}/retry", status_code=202)
async def retry_project(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin", "editor"}))):
    project = await _get_owned_project(project_id, db, principal)
    if project.status not in {"FAILED", "IDEA"}:
        raise HTTPException(409, "Retry is only available for failed or not-started projects")
    try:
        run = await WorkflowEngine(SessionLocal).retry(project.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"id": str(project.id), "workflow_id": str(run.id), "status": run.status, "started": True}


@router.get("/projects/{project_id}")
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await _get_owned_project(project_id, db, principal)
    runs_q = await db.execute(select(AgentRun).where(AgentRun.project_id == project.id).order_by(AgentRun.started_at.asc()))
    publications_q = await db.execute(select(Publication).where(Publication.project_id == project.id).order_by(Publication.created_at.desc()))
    workflows_q = await db.execute(select(WorkflowRun).where(WorkflowRun.project_id == project.id).order_by(WorkflowRun.created_at.desc()).limit(5))
    workflow_payload = []
    for wf in workflows_q.scalars().all():
        step_q = await db.execute(select(WorkflowStep).where(WorkflowStep.workflow_run_id == wf.id).order_by(WorkflowStep.step_order))
        workflow_payload.append({
            "id": str(wf.id), "status": wf.status, "attempt": wf.attempt, "current_step": wf.current_step,
            "last_error": wf.last_error,
            "steps": [{"step_key": step.step_key, "status": step.status, "attempts": step.attempts, "error_message": step.error_message} for step in step_q.scalars().all()],
        })
    return {
        "id": str(project.id),
        "topic": project.topic,
        "status": project.status,
        "data": project.data or {},
        "workflows": workflow_payload,
        "agent_runs": [{"id": str(run.id), "agent_name": run.agent_name, "status": run.status, "error_message": run.error_message, "started_at": run.started_at, "finished_at": run.finished_at} for run in runs_q.scalars().all()],
        "publications": [{"id": str(pub.id), "youtube_video_id": pub.youtube_video_id, "status": pub.status, "title": pub.title, "visibility": pub.visibility, "published_at": pub.published_at, "scheduled_at": pub.scheduled_at, "error_message": pub.error_message} for pub in publications_q.scalars().all()],
    }


def _safe_output_path(raw_path: str | None) -> Path:
    if not raw_path:
        raise HTTPException(404, "Rendered artifact not found")
    root = Path(settings.output_dir).resolve()
    path = Path(raw_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(403, "Artifact path is outside output directory") from exc
    return path


@router.get("/projects/{project_id}/video")
async def get_project_video(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await _get_owned_project(project_id, db, principal)
    path = _safe_output_path((project.data or {}).get("editor", {}).get("output_path"))
    if not path.exists():
        raise HTTPException(404, "Rendered video file does not exist")
    return FileResponse(path, media_type="video/mp4", filename=f"{project_id}.mp4")


@router.get("/projects/{project_id}/subtitles")
async def get_project_subtitles(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await _get_owned_project(project_id, db, principal)
    path = _safe_output_path((project.data or {}).get("editor", {}).get("subtitle_path"))
    if not path.exists():
        raise HTTPException(404, "Subtitle file does not exist")
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=f"{project_id}.srt")


@router.get("/projects/{project_id}/thumbnail")
async def get_project_thumbnail(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await _get_owned_project(project_id, db, principal)
    raw_path = (project.data or {}).get("thumbnail", {}).get("path")
    if raw_path:
        path = _safe_output_path(raw_path)
    else:
        path = _safe_output_path(str(Path(settings.output_dir) / str(project_id) / "thumbnail.png"))
    if not path.exists():
        raise HTTPException(404, "Thumbnail file does not exist")
    return FileResponse(path, media_type="image/png", filename=f"{project_id}-thumbnail.png")


@router.get("/projects/{project_id}/assets")
async def get_project_assets(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await _get_owned_project(project_id, db, principal)
    production = (project.data or {}).get("production", {})
    return {"project_id": str(project_id), "provider": production.get("provider"), "manifest_path": production.get("manifest_path"), "assets": production.get("assets", [])}
