from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, permission_dependency
from app.db.session import get_db
from app.models import Channel, VideoProject, ProductionMultimodalGraph
from app.multimodal_graph.service import MultimodalProductionGraphService

router = APIRouter(prefix="/api/v1/multimodal", tags=["multimodal-production-graph"])


def _assert_access(channel: Channel, principal: Principal):
    if principal.is_dev_fallback:
        return
    if principal.organization_id is not None and channel.organization_id == principal.organization_id:
        return
    if channel.owner_id == principal.scope_key:
        return
    raise HTTPException(404, "Project not found")


def _serialize(row: ProductionMultimodalGraph) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "channel_id": str(row.channel_id),
        "stage": row.stage,
        "status": row.status,
        "score": row.score,
        "risk_level": row.risk_level,
        "nodes": row.nodes,
        "edges": row.edges,
        "conflicts": row.conflicts,
        "recommendations": row.recommendations,
        "signals": row.signals,
        "created_at": row.created_at,
    }


async def _load(project_id: UUID, db: AsyncSession, principal: Principal) -> VideoProject:
    project = await db.get(VideoProject, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        raise HTTPException(404, "Channel not found")
    _assert_access(channel, principal)
    return project


@router.post("/projects/{project_id}/preflight")
async def multimodal_preflight(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    project = await _load(project_id, db, principal)
    result = await MultimodalProductionGraphService(db).build_preflight(project=project, organization_id=principal.organization_id)
    project.data = dict(project.data or {})
    project.data["multimodal_production_graph"] = result
    await db.commit()
    return result


@router.post("/projects/{project_id}/analyze")
async def multimodal_analyze(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    project = await _load(project_id, db, principal)
    result = await MultimodalProductionGraphService(db).analyze_rendered(project=project, organization_id=principal.organization_id)
    project.data = dict(project.data or {})
    project.data["multimodal_production_graph"] = result
    await db.commit()
    return result


@router.get("/projects/{project_id}/graphs")
async def multimodal_graphs(
    project_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    project = await _load(project_id, db, principal)
    rows = await db.execute(
        select(ProductionMultimodalGraph)
        .where(ProductionMultimodalGraph.project_id == project.id)
        .order_by(ProductionMultimodalGraph.created_at.desc())
        .limit(limit)
    )
    return {"project_id": str(project_id), "graphs": [_serialize(row) for row in rows.scalars().all()]}


@router.get("/projects/{project_id}/latest")
async def multimodal_latest(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    project = await _load(project_id, db, principal)
    row = await db.scalar(
        select(ProductionMultimodalGraph)
        .where(ProductionMultimodalGraph.project_id == project.id)
        .order_by(ProductionMultimodalGraph.created_at.desc())
    )
    return {"project_id": str(project_id), "graph": _serialize(row) if row else None}
