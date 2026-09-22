from __future__ import annotations

from uuid import UUID
import json

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, auth_db_dependency, enforce_csrf
from app.config import settings
from app.observability.access import metrics_token_matches
from app.models import (
    Channel,
    ContentExperiment,
    ContentPlan,
    OptimizationReport,
    VideoProject,
    WorkflowRun,
)
from app.models.research_scheduler import ResearchSchedule
from app.models.portfolio_manager import BudgetReservation
from app.models.portfolio import Portfolio

PUBLIC_SUFFIXES = {
    "/api/v1/health",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/youtube/oauth/callback",
    "/api/v1/billing/webhooks",
    "/api/v1/health/live",
    "/api/v1/health/ready",
}



def _is_public(request: Request) -> bool:
    if request.url.path in PUBLIC_SUFFIXES:
        return True
    if request.url.path == "/api/v1/metrics":
        if settings.app_env != "production" or settings.metrics_public:
            return True
        return metrics_token_matches(request)
    return False


async def _channel_for_id(db: AsyncSession, key: str, raw: str) -> Channel | None:
    try:
        rid = UUID(raw)
    except ValueError:
        raise ValueError(raw)
    if key == "channel_id":
        return await db.get(Channel, rid)
    project = await db.get(VideoProject, rid)
    return await db.get(Channel, project.channel_id) if project else None


async def _channel_for_path(db: AsyncSession, request: Request) -> Channel | None:
    params = request.path_params
    raw = params.get("channel_id")
    if raw:
        try:
            return await db.get(Channel, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid channel id")

    raw = params.get("project_id")
    if raw:
        try:
            project = await db.get(VideoProject, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid project id")
        if not project:
            return None
        return await db.get(Channel, project.channel_id)

    raw = params.get("workflow_id")
    if raw:
        try:
            workflow = await db.get(WorkflowRun, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid workflow id")
        if not workflow:
            return None
        project = await db.get(VideoProject, workflow.project_id)
        return await db.get(Channel, project.channel_id) if project else None

    raw = params.get("experiment_id")
    if raw:
        try:
            experiment = await db.get(ContentExperiment, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid experiment id")
        return await db.get(Channel, experiment.channel_id) if experiment else None

    raw = params.get("plan_id")
    if raw:
        try:
            plan = await db.get(ContentPlan, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid plan id")
        return await db.get(Channel, plan.channel_id) if plan else None

    raw = params.get("schedule_id")
    if raw:
        try:
            schedule = await db.get(ResearchSchedule, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid schedule id")
        return await db.get(Channel, schedule.channel_id) if schedule else None

    raw = params.get("report_id")
    if raw:
        try:
            report = await db.get(OptimizationReport, UUID(str(raw)))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid report id")
        if report and getattr(report, "video_project_id", None):
            project = await db.get(VideoProject, report.video_project_id)
            return await db.get(Channel, project.channel_id) if project else None

    return None


async def enforce_request_authorization(request: Request, db: AsyncSession = Depends(auth_db_dependency)) -> Principal | None:
    if _is_public(request):
        return None

    principal = getattr(request.state, "principal", None)
    if principal is None:
        from app.auth.security import resolve_principal
        principal = await resolve_principal(request, db)
        request.state.principal = principal

    if principal.is_dev_fallback:
        return principal

    await enforce_csrf(request, db, principal)

    # Read-only API keys are denied all mutations by default. Explicit write scopes can opt in.
    if principal.auth_type == "api-key" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if "*" not in principal.scopes and "write" not in principal.scopes and "content:write" not in principal.scopes and "publish" not in principal.scopes and "research:write" not in principal.scopes and "admin:manage" not in principal.scopes:
            raise HTTPException(status_code=403, detail="API key is read-only")

    # owner_id is a legacy tenant key. Authenticated APIs may no longer choose another tenant.
    supplied_owner = request.query_params.get("owner_id")
    if supplied_owner and supplied_owner != principal.scope_key:
        raise HTTPException(status_code=403, detail="Cross-organization owner_id is not allowed")

    # Legacy JSON payloads may carry owner_id. Authenticated callers cannot select another tenant.
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            raw = await request.body()
            if raw:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    body = {}
                if body.get("owner_id") and body["owner_id"] != principal.scope_key:
                    raise HTTPException(status_code=403, detail="Cross-organization owner_id is not allowed")
                for body_key in ("channel_id", "project_id"):
                    raw_resource = body.get(body_key)
                    if raw_resource:
                        try:
                            body_channel = await _channel_for_id(db, body_key, str(raw_resource))
                        except ValueError as exc:
                            raise HTTPException(status_code=400, detail=f"Invalid {body_key}") from exc
                        if body_channel is None:
                            raise HTTPException(status_code=404, detail="Resource not found")
                        if body_channel.organization_id and body_channel.organization_id != principal.organization_id:
                            raise HTTPException(status_code=404, detail="Resource not found")
                        if not body_channel.organization_id and body_channel.owner_id != principal.scope_key:
                            raise HTTPException(status_code=404, detail="Resource not found")
        except HTTPException:
            raise
        except (ValueError, TypeError):
            pass

    channel = await _channel_for_path(db, request)
    if channel:
        if channel.organization_id and channel.organization_id != principal.organization_id:
            raise HTTPException(status_code=404, detail="Resource not found")
        if not channel.organization_id and channel.owner_id != principal.scope_key:
            raise HTTPException(status_code=404, detail="Resource not found")
    elif any(key in request.path_params for key in ("channel_id", "project_id", "workflow_id", "experiment_id", "plan_id", "schedule_id", "report_id")):
        raise HTTPException(status_code=404, detail="Resource not found")

    # Portfolio resources use an explicit organization_id where available and otherwise legacy owner_id.
    if request.url.path.startswith("/api/v1/portfolio") or request.url.path.startswith("/api/v1/routing"):
        # Body owner_id is checked by the API handlers; this guard exists to reject obvious query spoofing.
        return principal

    return principal
