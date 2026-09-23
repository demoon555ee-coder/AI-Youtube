from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.security import Principal, permission_dependency
from app.models import Channel
from app.models.channel_memory import ChannelMemory
from app.schemas.brain import BrainRebuildRequest, VideoOptimizationRequest
from app.brain.service import rebuild_memory, optimize_video

router = APIRouter(prefix="/api/v1/brain", tags=["brain"])


async def _ensure_owned_channel(channel_id: str, db: AsyncSession, principal: Principal) -> None:
    try:
        channel = await db.get(Channel, channel_id)
    except Exception as exc:
        raise HTTPException(404, "Channel not found") from exc
    if not channel or ((channel.organization_id is not None and channel.organization_id != principal.organization_id) or (channel.organization_id is None and channel.owner_id != principal.scope_key)):
        raise HTTPException(404, "Channel not found")


@router.post("/channels/{channel_id}/rebuild")
async def rebuild_channel_brain(
    channel_id: str,
    payload: BrainRebuildRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    await _ensure_owned_channel(channel_id, db, principal)
    try:
        return await rebuild_memory(db, channel_id, payload.min_video_count)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/channels/{channel_id}")
async def get_channel_brain(channel_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("read"))):
    await _ensure_owned_channel(channel_id, db, principal)
    q = await db.execute(select(ChannelMemory).where(ChannelMemory.channel_id == channel_id))
    memory = q.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Channel brain has not been built yet")
    return {
        "channel_id": channel_id,
        "source_video_count": memory.source_video_count,
        "version": memory.version,
        "summary": memory.summary,
        "learned_patterns": memory.learned_patterns,
        "topic_clusters": memory.topic_clusters,
        "hook_patterns": memory.hook_patterns,
        "title_patterns": memory.title_patterns,
        "pacing_patterns": memory.pacing_patterns,
        "production_notes": memory.production_notes,
        "last_analyzed_at": memory.last_analyzed_at,
    }


@router.post("/channels/{channel_id}/optimize-video")
async def optimize_channel_video(
    channel_id: str,
    payload: VideoOptimizationRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(permission_dependency("content:write")),
):
    await _ensure_owned_channel(channel_id, db, principal)
    try:
        return await optimize_video(db, channel_id, payload.video_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
