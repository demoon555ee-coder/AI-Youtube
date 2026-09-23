from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import quote
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Channel, VideoProject, YouTubeConnection
from app.schemas.youtube import YouTubeOAuthStart, PublishRequest, AnalyticsRequest
from app.services.audit import write_audit
from app.services.youtube_service import create_oauth_url, finish_oauth, analytics, connection_status
from app.config import settings
from app.auth.security import Principal, get_current_principal, require_roles
from app.runtime.service import AgentRuntimeService, AgentRuntimeError
from decimal import Decimal

router = APIRouter(prefix="/api/v1/youtube", tags=["youtube"])


@router.post("/oauth/start")
async def oauth_start(payload: YouTubeOAuthStart, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return {"authorization_url": await create_oauth_url(db, principal.scope_key)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Request failed" if settings.app_env == "production" else str(exc))


@router.get("/oauth/callback")
async def oauth_callback(request: Request, db: AsyncSession = Depends(get_db)):
    state = request.query_params.get("state")
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state")
    try:
        result = await finish_oauth(db, str(request.url), state)
        redirect = f"{settings.frontend_url.rstrip("/")}/settings?youtube=connected&channel_id={result["channel_id"]}"
        return RedirectResponse(url=redirect, status_code=303)
    except Exception as exc:
        redirect = f"{settings.frontend_url.rstrip("/")}/settings?youtube=error&message={quote(str(exc)[:160])}"
        return RedirectResponse(url=redirect, status_code=303)


@router.get("/channels/{channel_id}/status")
async def youtube_status(channel_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return await connection_status(db, channel_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/channels/{channel_id}/connection")
async def youtube_disconnect(
    channel_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(require_roles({"owner", "admin"})),
):
    try:
        cid = UUID(channel_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid channel id") from exc

    channel = await db.get(Channel, cid)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.organization_id is not None:
        if channel.organization_id != principal.organization_id:
            raise HTTPException(status_code=403, detail="Channel access denied")
    elif channel.owner_id != principal.scope_key:
        raise HTTPException(status_code=403, detail="Channel access denied")

    connection = await db.scalar(select(YouTubeConnection).where(YouTubeConnection.channel_id == cid))
    if connection:
        await db.delete(connection)
        await write_audit(
            db,
            request,
            principal,
            action="youtube.disconnect",
            resource_type="channel",
            resource_id=str(channel.id),
            metadata={"youtube_channel_id": channel.youtube_channel_id},
        )
        await db.commit()

    return {
        "ok": True,
        "channel_id": str(channel.id),
        "youtube_channel_id": channel.youtube_channel_id,
        "connected": False,
    }


@router.post("/channels/{channel_id}/publish", status_code=202)
async def youtube_publish(channel_id: str, payload: PublishRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_roles({"owner", "admin"}))):
    # Manual publishing is an intent, not a privileged shortcut. The task is admitted
    # by Governance and executed later by the leased Publisher Agent.
    channel = await db.get(Channel, channel_id)
    project = await db.get(VideoProject, payload.project_id)
    if not channel or not project or project.channel_id != channel.id:
        raise HTTPException(status_code=404, detail="Channel or project not found")
    try:
        task = await AgentRuntimeService(db).create_task(
            channel_id=channel.id,
            agent_key="publisher",
            task_type="publisher",
            action_type="publish",
            input_data=payload.model_dump(),
            budget_usd=Decimal("0.5"),
            confidence=0.90,
            requested_mode="approve",
            idempotency_key=f"publish:{project.id}:{payload.publish_at or 'immediate'}:{payload.privacy_status}",
            project_id=project.id,
        )
    except AgentRuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return {
        "task_id": str(task.id),
        "status": task.status,
        "governance_mode": task.governance_mode,
        "governance_approved": task.governance_approved,
        "message": "Publish request admitted to the governed execution queue.",
    }


@router.post("/channels/{channel_id}/analytics")
async def youtube_analytics(channel_id: str, payload: AnalyticsRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return await analytics(db, channel_id, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
