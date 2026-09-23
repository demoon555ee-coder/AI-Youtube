from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.auth.security import Principal, get_current_principal
from app.config import settings
from app.routing import ProviderRouter
from app.schemas.routing import ProviderProfileRequest, RouteRequest, ProjectRouteRequest

router = APIRouter(prefix="/api/v1/routing", tags=["routing"])


@router.get("/providers")
async def providers(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    rows = await ProviderRouter(db).profiles(principal.scope_key)
    return {"profiles": [
        {"id": str(r.id), "provider": r.provider, "service": r.service, "kind": r.kind,
         "quality_tier": r.quality_tier, "priority": r.priority, "unit": r.unit,
         "unit_cost_usd": r.unit_cost_usd, "enabled": r.enabled,
         "capabilities": r.capabilities or {}, "config": {k: v for k, v in (r.config_json or {}).items() if k != "api_key"}}
        for r in rows
    ]}


@router.post("/providers")
async def configure_provider(payload: ProviderProfileRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if "api_key" in payload.config:
        raise HTTPException(400, "Do not store raw API keys in config; use api_key_env")
    try:
        row = await ProviderRouter(db).configure_profile(
            principal.scope_key, provider=payload.provider, service=payload.service, kind=payload.kind,
            quality_tier=payload.quality_tier, priority=payload.priority, unit=payload.unit,
            unit_cost_usd=payload.unit_cost_usd, capabilities=payload.capabilities,
            config_json=payload.config, enabled=payload.enabled,
        )
        return {"id": str(row.id), "provider": row.provider, "service": row.service, "kind": row.kind,
                "quality_tier": row.quality_tier, "priority": row.priority, "unit": row.unit,
                "unit_cost_usd": row.unit_cost_usd, "enabled": row.enabled}
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/route")
async def route_once(payload: RouteRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return await ProviderRouter(db).route(
            owner_id=principal.scope_key, service=payload.service, requested_tier=payload.requested_tier,
            units=payload.units, channel_id=UUID(payload.channel_id) if payload.channel_id else None,
            project_id=UUID(payload.project_id) if payload.project_id else None,
            step_name=payload.step_name, required_capabilities=payload.required_capabilities,
            allow_quality_downgrade=payload.allow_quality_downgrade,
        )
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/project-plan")
async def route_project(payload: ProjectRouteRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return {"routes": await ProviderRouter(db).project_plan(
            owner_id=principal.scope_key, channel_id=UUID(payload.channel_id), project_id=UUID(payload.project_id),
            goal=payload.goal, quality_mode=payload.quality_mode,
        )}
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.get("/runtime-availability")
async def runtime_availability(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if not settings.provider_health_enabled:
        raise HTTPException(404, "Provider health is disabled")
    router = ProviderRouter(db)
    portfolio = await router.ensure_portfolio(principal.scope_key)
    services = ("llm", "research", "visual", "tts", "render", "image", "video")
    payload = {}
    for service in services:
        candidates = await router.candidates(portfolio.id, service)
        payload[service] = [
            {
                "provider": candidate.provider,
                "kind": candidate.kind,
                "tier": candidate.tier,
                "priority": candidate.priority,
                "runtime_available": candidate.runtime_available,
                "capabilities": candidate.capabilities or {},
            }
            for candidate in candidates
        ]
    return {"enabled": True, "services": payload}


@router.get("/decisions")
async def decisions(limit: int = 100, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    rows = await ProviderRouter(db).decisions(principal.scope_key, limit)
    return {"decisions": [
        {"id": str(r.id), "step_name": r.step_name, "service": r.service, "requested_tier": r.requested_tier,
         "chosen_provider": r.chosen_provider, "chosen_tier": r.chosen_tier, "fallback_used": r.fallback_used,
         "estimated_cost_usd": r.estimated_cost_usd, "reason": r.reason, "candidates": r.candidates_json,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]}
