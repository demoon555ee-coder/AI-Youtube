from __future__ import annotations
from uuid import UUID
import copy
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.security import Principal, get_current_principal, permission_dependency
from app.db.session import get_db
from app.config import settings
from app.models import Channel, CreativeAnalysis, VideoProject
from app.creative_intelligence import CreativeIntelligenceService
from app.creative_intelligence.service import TargetedReEditService
from app.evolution.service import ContentEvolutionService
from app.quality.service import VideoQualityService

router = APIRouter(prefix="/api/v1/creative", tags=["creative-intelligence"])

class ReEditRequest(BaseModel):
    analysis_id: UUID | None = None
    director_plan_id: UUID | None = None
    scenes: list[dict] = Field(default_factory=list)
    reason: str = "Targeted creative re-edit"



def _assert_access(channel: Channel, principal: Principal):
    if principal.is_dev_fallback:
        return
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return
    if channel.owner_id == principal.scope_key:
        return
    raise HTTPException(404, "Project not found")

def _serialize(row: CreativeAnalysis):
    return {
        "id": str(row.id), "project_id": str(row.project_id), "channel_id": str(row.channel_id),
        "stage": row.stage, "status": row.status, "score": row.score, "sampled_frames": row.sampled_frames,
        "scene_reports": row.scene_reports, "audio_analysis": row.audio_analysis, "visual_analysis": row.visual_analysis,
        "issues": row.issues, "recommendations": row.recommendations, "reedit_plan": row.reedit_plan, "created_at": row.created_at,
    }

@router.post("/projects/{project_id}/analyze")
async def analyze(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    result = await CreativeIntelligenceService(db).analyze(project=project, stage="manual", organization_id=principal.organization_id)
    await db.commit()
    return result

@router.get("/projects/{project_id}/analyses")
async def list_analyses(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    rows = await db.execute(select(CreativeAnalysis).where(CreativeAnalysis.project_id == project_id).order_by(CreativeAnalysis.created_at.desc()).limit(20))
    return {"project_id": str(project_id), "analyses": [_serialize(x) for x in rows.scalars().all()]}


@router.post("/projects/{project_id}/reedit", status_code=201)
async def targeted_reedit(project_id: UUID, payload: ReEditRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("content:write"))):
    source = await db.get(VideoProject, project_id, with_for_update=True)
    if not source:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, source.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    if source.status not in {"READY_TO_PUBLISH", "PUBLISHED", "COMPLETED"}:
        raise HTTPException(409, "Project must be complete before targeted re-edit")
    analysis = None
    if payload.analysis_id:
        analysis = await db.get(CreativeAnalysis, payload.analysis_id)
        if not analysis or analysis.project_id != source.id:
            raise HTTPException(400, "Invalid creative analysis")
    director_plan = None
    if payload.director_plan_id:
        director_plan = await db.get(CreativeDirectorDecision, payload.director_plan_id)
        if not director_plan or director_plan.project_id != source.id:
            raise HTTPException(400, "Invalid director plan")
    patches = list(payload.scenes or ((director_plan.plan or {}).get("changes", []) if director_plan else []) or ((analysis.reedit_plan or {}).get("scenes", []) if analysis else []))
    executable = [
        {**item, "prompt": str((item.get("parameters") or {}).get("prompt") or item.get("prompt") or "Improve the scene visual.")}
        for item in patches
        if item.get("action", "replace_visual") in {"replace_visual", "tighten"}
    ]
    if not executable:
        raise HTTPException(400, "No automatically executable scene instructions supplied")
    patches = executable

    evolution = ContentEvolutionService(db)
    revision, version = await evolution.create_revision(
        source_project=source, trigger_type="creative_reedit", reason=payload.reason,
        change_plan={"mode": "targeted_scene_reedit", "scenes": patches, "director_plan_id": str(director_plan.id) if director_plan else None},
        metrics_snapshot={"analysis_id": str(analysis.id) if analysis else None, "director_plan_id": str(director_plan.id) if director_plan else None},
        trigger_alert_id=None,
    )
    inherited = copy.deepcopy(source.data or {})
    for key in ("scene_director", "storyboard", "production", "thumbnail"):
        if key in inherited:
            revision.data[key] = inherited[key]
    try:
        render = await TargetedReEditService(settings.output_dir).render_patch(
            source_project=source, revision_project_id=str(revision.id), scene_patches=patches
        )
        revision.data["editor"] = render
        revision.data["evolution"]["render"] = render
        quality = await VideoQualityService(db).evaluate(project=revision, output=render, stage="targeted_reedit")
        creative = await CreativeIntelligenceService(db).analyze(project=revision, stage="targeted_reedit", organization_id=principal.organization_id)
        revision.data["qa"] = quality
        revision.data["creative_intelligence"] = creative
        revision.status = "READY_TO_PUBLISH" if quality.get("status") != "FAIL" else "FAILED"
        await evolution.update_status(revision.id, "READY_TO_PUBLISH" if revision.status == "READY_TO_PUBLISH" else "FAILED")
        await evolution.register_project_artifacts(revision)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {
        "version_id": str(version.id), "project_id": str(revision.id), "revision_number": revision.revision_number,
        "status": revision.status, "render": render, "quality": quality, "creative_analysis": creative,
    }

from app.models import CreativeDirectorDecision
from app.creative_director import CreativeDirectorService

class DirectorPlanRequest(BaseModel):
    analysis_id: UUID | None = None
    max_changes: int = Field(default=3, ge=0, le=12)


def _serialize_director(row: CreativeDirectorDecision):
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "analysis_id": str(row.analysis_id) if row.analysis_id else None,
        "status": row.status,
        "max_changes": row.max_changes,
        "score": row.score,
        "plan": row.plan or {},
        "execution": row.execution_summary or {},
        "created_at": row.created_at,
    }


@router.post("/projects/{project_id}/director-plan", status_code=201)
async def create_director_plan(
    project_id: UUID,
    payload: DirectorPlanRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    analysis = None
    if payload.analysis_id:
        analysis = await db.get(CreativeAnalysis, payload.analysis_id)
        if not analysis or analysis.project_id != project.id:
            raise HTTPException(400, "Invalid creative analysis")
    else:
        analysis = await db.scalar(
            select(CreativeAnalysis)
            .where(CreativeAnalysis.project_id == project.id)
            .order_by(CreativeAnalysis.created_at.desc())
        )
    if not analysis:
        raise HTTPException(409, "Run creative analysis before requesting a director plan")
    blueprint = (project.data or {}).get("content_blueprint") or (project.data or {}).get("blueprint") or {}
    routing = (project.data or {}).get("routing_plan") or {}
    director_route = routing.get("creative_director") or routing.get("scene_director") or {}
    service = CreativeDirectorService(
        llm_provider=director_route.get("provider"),
        llm_config=director_route.get("config") or {},
    )
    plan = await service.build_plan(project=project, analysis=_serialize(analysis), blueprint=blueprint, max_changes=payload.max_changes)
    row = CreativeDirectorDecision(
        organization_id=channel.organization_id,
        channel_id=channel.id,
        project_id=project.id,
        analysis_id=analysis.id,
        status=plan.get("status", "READY"),
        max_changes=payload.max_changes,
        score=float(analysis.score or 0),
        plan=plan,
        execution_summary=plan.get("execution", {}),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _serialize_director(row)


@router.get("/projects/{project_id}/director-plans")
async def list_director_plans(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    rows = await db.execute(
        select(CreativeDirectorDecision)
        .where(CreativeDirectorDecision.project_id == project.id)
        .order_by(CreativeDirectorDecision.created_at.desc())
        .limit(20)
    )
    return {"project_id": str(project.id), "plans": [_serialize_director(x) for x in rows.scalars().all()]}
