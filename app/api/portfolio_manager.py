from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.auth.security import Principal, get_current_principal
from app.portfolio.manager import PortfolioManager
from app.schemas.portfolio_manager import PortfolioPolicyRequest, ReserveRequest, ForecastRequest

router = APIRouter(prefix="/api/v1/portfolio/manager", tags=["portfolio-manager"])


def _policy(row):
    return {"id": str(row.id), "portfolio_id": str(row.portfolio_id), "planning_horizon_days": row.planning_horizon_days,
            "reserve_ratio": row.reserve_ratio, "target_utilization_pct": row.target_utilization_pct,
            "max_channel_concentration_pct": row.max_channel_concentration_pct, "min_channel_allocation_usd": row.min_channel_allocation_usd,
            "min_daily_buffer_usd": row.min_daily_buffer_usd, "enabled": row.enabled}


@router.get("/policy")
async def get_policy(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    return {"policy": _policy(await PortfolioManager(db).policy(principal.scope_key))}


@router.post("/policy")
async def set_policy(payload: PortfolioPolicyRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        values = payload.model_dump(exclude={"owner_id"}, exclude_none=True)
        return {"policy": _policy(await PortfolioManager(db).configure_policy(principal.scope_key, **values))}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/rebalance")
async def rebalance(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        rows = await PortfolioManager(db).rebalance(principal.scope_key)
        return {"allocations": [{"id": str(r.id), "channel_id": str(r.channel_id), "allocation_date": r.allocation_date.isoformat(),
                                  "target_budget_usd": r.target_budget_usd, "projected_spend_usd": r.projected_spend_usd,
                                  "budget_weight": r.budget_weight, "fairness_score": r.fairness_score, "rank": r.rank, "status": r.status} for r in rows]}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/allocations")
async def allocations(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    from sqlalchemy import select
    from app.models import Portfolio
    from app.models.portfolio_manager import PortfolioAllocation
    portfolio = await PortfolioManager(db)._portfolio(principal.scope_key)
    rows = await db.execute(select(PortfolioAllocation).where(PortfolioAllocation.portfolio_id == portfolio.id).order_by(PortfolioAllocation.allocation_date.desc(), PortfolioAllocation.rank.asc()).limit(200))
    return {"allocations": [{"id": str(r.id), "channel_id": str(r.channel_id), "allocation_date": r.allocation_date.isoformat(),
                              "target_budget_usd": r.target_budget_usd, "reserved_budget_usd": r.reserved_budget_usd,
                              "projected_spend_usd": r.projected_spend_usd, "budget_weight": r.budget_weight, "fairness_score": r.fairness_score,
                              "rank": r.rank, "status": r.status, "metadata": r.metadata_json} for r in rows.scalars().all()]}


@router.get("/queue")
async def queue(limit: int = 100, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    return await PortfolioManager(db).queue_snapshot(principal.scope_key, limit)


@router.post("/reserve")
async def reserve(payload: ReserveRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        row = await PortfolioManager(db).reserve(
            principal.scope_key, amount_usd=payload.amount_usd, idempotency_key=payload.idempotency_key,
            channel_id=UUID(payload.channel_id) if payload.channel_id else None,
            project_id=UUID(payload.project_id) if payload.project_id else None,
            purpose=payload.purpose, ttl_minutes=payload.ttl_minutes,
        )
        return {"reservation": {"id": str(row.id), "amount_usd": row.amount_usd, "status": row.status, "expires_at": row.expires_at.isoformat(), "idempotency_key": row.idempotency_key}}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/release/{reservation_id}")
async def release(reservation_id: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        row = await PortfolioManager(db).release(principal.scope_key, reservation_id)
        return {"reservation": {"id": str(row.id), "status": row.status, "released_at": row.released_at.isoformat() if row.released_at else None}}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/release-expired")
async def release_expired(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return {"released": await PortfolioManager(db).release_expired(principal.scope_key)}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/forecast")
async def forecast(payload: ForecastRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    try:
        return await PortfolioManager(db).forecast(principal.scope_key, days=payload.days, average_video_cost_usd=payload.average_video_cost_usd)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
