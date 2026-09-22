from app.config import settings
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.portfolio.service import PortfolioService
from app.schemas.portfolio import PortfolioConfigureRequest, PortfolioChannelRequest, ProviderBudgetRequest, CostEventRequest
from app.auth.security import Principal, get_current_principal

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get("/overview")
async def portfolio_overview(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return await PortfolioService(db).overview(principal.scope_key)
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/configure")
async def portfolio_configure(payload: PortfolioConfigureRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        row = await PortfolioService(db).configure(principal.scope_key, name=payload.name, monthly_budget_usd=payload.monthly_budget_usd, daily_budget_usd=payload.daily_budget_usd)
        return {"id": str(row.id), "owner_id": row.owner_id, "name": row.name, "monthly_budget_usd": row.monthly_budget_usd, "daily_budget_usd": row.daily_budget_usd, "currency": row.currency}
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/channels/{channel_id}/attach")
async def portfolio_attach_channel(channel_id: UUID, payload: PortfolioChannelRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        row = await PortfolioService(db).attach_channel(principal.scope_key, channel_id, budget_weight=payload.budget_weight, monthly_budget_usd=payload.monthly_budget_usd)
        return {"id": str(row.id), "portfolio_id": str(row.portfolio_id), "channel_id": str(row.channel_id), "budget_weight": row.budget_weight, "monthly_budget_usd": row.monthly_budget_usd, "active": row.active}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/provider-budgets")
async def portfolio_provider_budget(payload: ProviderBudgetRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        row = await PortfolioService(db).set_provider_budget(principal.scope_key, provider=payload.provider, service=payload.service, monthly_limit_usd=payload.monthly_limit_usd, daily_limit_usd=payload.daily_limit_usd, hard_limit=payload.hard_limit)
        return {"id": str(row.id), "provider": row.provider, "service": row.service, "monthly_limit_usd": row.monthly_limit_usd, "daily_limit_usd": row.daily_limit_usd, "hard_limit": row.hard_limit}
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.post("/cost-events")
async def portfolio_cost_event(payload: CostEventRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        event = await PortfolioService(db).record_cost(
            principal.scope_key, provider=payload.provider, service=payload.service, unit=payload.unit,
            quantity=payload.quantity, unit_cost_usd=payload.unit_cost_usd,
            channel_id=UUID(payload.channel_id) if payload.channel_id else None,
            project_id=UUID(payload.project_id) if payload.project_id else None,
            agent_run_id=UUID(payload.agent_run_id) if payload.agent_run_id else None,
            metadata_json=payload.metadata,
        )
        return {"id": str(event.id), "portfolio_id": str(event.portfolio_id), "total_cost_usd": event.total_cost_usd}
    except ValueError as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc


@router.get("/cost-check")
async def portfolio_cost_check(
    provider: str = "",
    service: str = "general",
    estimated_cost_usd: float = 0,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if not provider:
        raise HTTPException(400, "provider is required")
    if estimated_cost_usd < 0:
        raise HTTPException(400, "estimated_cost_usd must be non-negative")
    try:
        portfolio = await PortfolioService(db).ensure(principal.scope_key)
        from datetime import datetime
        from sqlalchemy import func, select
        from app.models.portfolio import CostEvent, ProviderBudget
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        day_start = datetime(now.year, now.month, now.day)
        budget = await db.scalar(select(ProviderBudget).where(ProviderBudget.portfolio_id == portfolio.id, ProviderBudget.provider == provider, ProviderBudget.service == service))
        monthly = float(await db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(CostEvent.portfolio_id == portfolio.id, CostEvent.provider == provider, CostEvent.service == service, CostEvent.created_at >= month_start)) or 0)
        daily = float(await db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(CostEvent.portfolio_id == portfolio.id, CostEvent.provider == provider, CostEvent.service == service, CostEvent.created_at >= day_start)) or 0)
        monthly_limit = budget.monthly_limit_usd if budget else 0
        daily_limit = budget.daily_limit_usd if budget else 0
        monthly_ok = monthly_limit <= 0 or monthly + estimated_cost_usd <= monthly_limit
        daily_ok = daily_limit <= 0 or daily + estimated_cost_usd <= daily_limit
        return {
            "allowed": bool(monthly_ok and daily_ok),
            "hard_limit": bool(budget.hard_limit) if budget else False,
            "provider": provider, "service": service, "estimated_cost_usd": estimated_cost_usd,
            "monthly": {"spent_usd": monthly, "limit_usd": monthly_limit, "after_usd": monthly + estimated_cost_usd, "within_limit": monthly_ok},
            "daily": {"spent_usd": daily, "limit_usd": daily_limit, "after_usd": daily + estimated_cost_usd, "within_limit": daily_ok},
        }
    except Exception as exc:
        raise HTTPException(500 if settings.app_env == "production" else 400, "Request failed" if settings.app_env == "production" else str(exc)) from exc
