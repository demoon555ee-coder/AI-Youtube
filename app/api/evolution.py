from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, permission_dependency
from app.db.session import SessionLocal, get_db
from app.models import Channel, ContentArtifact, ContentVersion, PerformanceAlert, VideoProject
from app.evolution.service import ContentEvolutionService, build_evolution_plan
from app.workflows.engine import WorkflowEngine

router = APIRouter(prefix="/api/v1/evolution", tags=["content-evolution"])


class RevisionRequest(BaseModel):
    trigger_type: str = Field(default="manual", min_length=2, max_length=40)
    reason: str = Field(min_length=3, max_length=2000)
    change_plan: dict = Field(default_factory=dict)
    metrics_snapshot: dict = Field(default_factory=dict)
    trigger_alert_id: UUID | None = None
    auto_run: bool = False


def _assert_project_access(project: VideoProject, channel: Channel, principal: Principal) -> None:
    if principal.is_dev_fallback:
        return
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return
    if channel.owner_id == principal.scope_key:
        return
    raise HTTPException(status_code=404, detail="Project not found")


@router.get("/projects/{project_id}/versions")
async def list_project_versions(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_project_access(project, channel, principal)
    root_id = project.content_root_id or project.id
    rows = await ContentEvolutionService(db).list_versions(root_id)
    project_ids = [row.project_id for row in rows]
    projects_q = await db.execute(select(VideoProject).where(VideoProject.id.in_(project_ids))) if project_ids else None
    by_id = {p.id: p for p in (projects_q.scalars().all() if projects_q else [])}
    return {
        "content_root_id": str(root_id),
        "versions": [
            {
                "id": str(v.id),
                "project_id": str(v.project_id),
                "parent_project_id": str(v.parent_project_id) if v.parent_project_id else None,
                "revision_number": v.revision_number,
                "trigger_type": v.trigger_type,
                "reason": v.reason,
                "change_plan": v.change_plan,
                "metrics_snapshot": v.metrics_snapshot,
                "status": v.status,
                "project_status": by_id.get(v.project_id).status if by_id.get(v.project_id) else None,
                "created_at": v.created_at,
            }
            for v in rows
        ],
    }


@router.get("/projects/{project_id}/artifacts")
async def list_project_artifacts(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_project_access(project, channel, principal)
    q = await db.execute(select(ContentArtifact).where(ContentArtifact.project_id == project_id).order_by(ContentArtifact.created_at.asc()))
    return {"project_id": str(project_id), "artifacts": [{
        "id": str(x.id), "artifact_type": x.artifact_type, "relative_path": x.relative_path,
        "sha256": x.sha256, "size_bytes": x.size_bytes, "immutable": x.immutable,
        "metadata": x.metadata_json, "created_at": x.created_at,
    } for x in q.scalars().all()]}


@router.post("/projects/{project_id}/revisions", status_code=201)
async def create_revision(
    project_id: UUID,
    payload: RevisionRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    source = await db.get(VideoProject, project_id, with_for_update=True)
    if not source:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, source.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_project_access(source, channel, principal)
    if source.status in {"QUEUED", "RESEARCHING", "SCRIPTING", "STORYBOARDING", "DIRECTING_SCENES", "GENERATING_ASSETS", "EDITING", "GENERATING_THUMBNAIL", "QA"}:
        raise HTTPException(409, "Source project is still running")

    if payload.trigger_alert_id:
        alert = await db.get(PerformanceAlert, payload.trigger_alert_id)
        publication = await db.scalar(select(Publication).where(Publication.project_id == source.id, Publication.youtube_video_id == (alert.youtube_video_id if alert else "")))
        if not alert or alert.channel_id != source.channel_id or not publication:
            # A project may not inherit an alert from another channel or unrelated published video.
            raise HTTPException(400, "Invalid trigger alert for source project")

    plan = payload.change_plan or build_evolution_plan(
        alert_type=None,
        metric=(payload.metrics_snapshot or {}).get("metric"),
        delta_pct=(payload.metrics_snapshot or {}).get("delta_pct"),
        evidence=(payload.metrics_snapshot or {}).get("evidence"),
    )
    try:
        revision, version = await ContentEvolutionService(db).create_revision(
            source_project=source,
            trigger_type=payload.trigger_type,
            reason=payload.reason,
            change_plan=plan,
            metrics_snapshot=payload.metrics_snapshot,
            trigger_alert_id=payload.trigger_alert_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    workflow_id = None
    run_started = False
    if payload.auto_run:
        try:
            run = await WorkflowEngine(SessionLocal).create_or_get(revision.id, f"evolution:{version.id}")
            workflow_id = str(run.id)
            run_started = True
        except Exception:
            # Revision remains safely available for manual start.
            run_started = False
    return {
        "version_id": str(version.id),
        "project_id": str(revision.id),
        "content_root_id": str(version.content_root_id),
        "parent_project_id": str(source.id),
        "revision_number": version.revision_number,
        "status": revision.status,
        "workflow_id": workflow_id,
        "run_started": run_started,
        "change_plan": plan,
    }
