from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.security import Principal, get_current_principal
from app.models import VideoProject, VideoQualityReport
from app.quality.service import VideoQualityService

router = APIRouter(prefix="/api/v1/quality", tags=["quality"])


def _serialize(row: VideoQualityReport) -> dict:
    return {
        "id": str(row.id), "project_id": str(row.project_id), "channel_id": str(row.channel_id),
        "stage": row.stage, "status": row.status, "score": row.score,
        "duration_seconds": row.duration_seconds, "width": row.width, "height": row.height,
        "checks": row.checks, "issues": row.issues, "recommendations": row.recommendations,
        "created_at": row.created_at,
    }

@router.get("/projects/{project_id}/reports")
async def quality_reports(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    q = await db.execute(select(VideoQualityReport).where(VideoQualityReport.project_id == project_id).order_by(VideoQualityReport.created_at.desc()).limit(20))
    return {"project_id": str(project_id), "reports": [_serialize(x) for x in q.scalars().all()]}

@router.post("/projects/{project_id}/run")
async def quality_run(project_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    output = (project.data or {}).get("editor", {})
    result = await VideoQualityService(db).evaluate(project=project, output=output, stage="manual")
    await db.commit()
    return result
