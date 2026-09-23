from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Channel
from app.models.portfolio import Portfolio, PortfolioChannel, ProviderBudget, CostEvent
from app.portfolio.intelligence import budget_status


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class PortfolioService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure(self, owner_id: str = "local-user") -> Portfolio:
        row = await self.db.scalar(select(Portfolio).where(Portfolio.owner_id == owner_id))
        if row:
            if row.organization_id is None:
                try:
                    row.organization_id = uuid.UUID(owner_id)
                except (ValueError, AttributeError):
                    pass
            await self.sync_channels(row)
            return row
        organization_id = None
        try:
            organization_id = uuid.UUID(owner_id)
        except (ValueError, AttributeError):
            organization_id = None
        row = Portfolio(owner_id=owner_id, organization_id=organization_id, name="My YouTube Portfolio", currency="USD")
        self.db.add(row)
        await self.db.flush()
        await self.sync_channels(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def sync_channels(self, portfolio: Portfolio) -> None:
        channels = (await self.db.execute(
            select(Channel).where(Channel.owner_id == portfolio.owner_id).order_by(Channel.created_at.asc())
        )).scalars().all()
        linked = set((await self.db.execute(
            select(PortfolioChannel.channel_id).where(PortfolioChannel.portfolio_id == portfolio.id)
        )).scalars().all())
        for channel in channels:
            if channel.id not in linked:
                self.db.add(PortfolioChannel(portfolio_id=portfolio.id, channel_id=channel.id))

    async def attach_channel(self, owner_id: str, channel_id: uuid.UUID, *, budget_weight: float = 1.0, monthly_budget_usd: float = 0.0) -> PortfolioChannel:
        portfolio = await self.ensure(owner_id)
        channel = await self.db.get(Channel, channel_id)
        if not channel or channel.owner_id != owner_id:
            raise ValueError("Channel not found for owner")
        row = await self.db.scalar(select(PortfolioChannel).where(
            PortfolioChannel.portfolio_id == portfolio.id,
            PortfolioChannel.channel_id == channel.id,
        ))
        if row:
            row.budget_weight = max(0.0, budget_weight)
            row.monthly_budget_usd = max(0.0, monthly_budget_usd)
        else:
            row = PortfolioChannel(
                portfolio_id=portfolio.id, channel_id=channel.id,
                budget_weight=max(0.0, budget_weight), monthly_budget_usd=max(0.0, monthly_budget_usd)
            )
            self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def configure(self, owner_id: str, *, name: str | None = None, monthly_budget_usd: float | None = None, daily_budget_usd: float | None = None) -> Portfolio:
        portfolio = await self.ensure(owner_id)
        if name is not None:
            portfolio.name = name.strip() or portfolio.name
        if monthly_budget_usd is not None:
            portfolio.monthly_budget_usd = max(0.0, monthly_budget_usd)
        if daily_budget_usd is not None:
            portfolio.daily_budget_usd = max(0.0, daily_budget_usd)
        await self.db.commit()
        await self.db.refresh(portfolio)
        return portfolio

    async def set_provider_budget(self, owner_id: str, *, provider: str, service: str = "general", monthly_limit_usd: float = 0.0, daily_limit_usd: float = 0.0, hard_limit: bool = False) -> ProviderBudget:
        portfolio = await self.ensure(owner_id)
        row = await self.db.scalar(select(ProviderBudget).where(
            ProviderBudget.portfolio_id == portfolio.id,
            ProviderBudget.provider == provider,
            ProviderBudget.service == service,
        ))
        if not row:
            row = ProviderBudget(portfolio_id=portfolio.id, provider=provider, service=service)
            self.db.add(row)
        row.monthly_limit_usd = max(0.0, monthly_limit_usd)
        row.daily_limit_usd = max(0.0, daily_limit_usd)
        row.hard_limit = hard_limit
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def record_cost(self, owner_id: str, *, provider: str, service: str, unit: str, quantity: float, unit_cost_usd: float, channel_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None, agent_run_id: uuid.UUID | None = None, metadata_json: dict | None = None) -> CostEvent:
        portfolio = await self.ensure(owner_id)
        total = round(max(0.0, quantity) * max(0.0, unit_cost_usd), 8)
        budget = await self.db.scalar(select(ProviderBudget).where(
            ProviderBudget.portfolio_id == portfolio.id,
            ProviderBudget.provider == provider,
            ProviderBudget.service == service,
        ).with_for_update())
        if budget and budget.hard_limit:
            now = _utcnow()
            month_start = datetime(now.year, now.month, 1)
            day_start = datetime(now.year, now.month, now.day)
            monthly_spend = float(await self.db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id, CostEvent.provider == provider, CostEvent.service == service, CostEvent.created_at >= month_start,
            )) or 0)
            daily_spend = float(await self.db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id, CostEvent.provider == provider, CostEvent.service == service, CostEvent.created_at >= day_start,
            )) or 0)
            if budget.monthly_limit_usd > 0 and monthly_spend + total > budget.monthly_limit_usd:
                raise ValueError(f"Provider monthly hard limit exceeded for {provider}/{service}")
            if budget.daily_limit_usd > 0 and daily_spend + total > budget.daily_limit_usd:
                raise ValueError(f"Provider daily hard limit exceeded for {provider}/{service}")
        event = CostEvent(
            owner_id=owner_id, portfolio_id=portfolio.id, channel_id=channel_id,
            project_id=project_id, agent_run_id=agent_run_id, provider=provider,
            service=service, unit=unit, quantity=max(0.0, quantity),
            unit_cost_usd=max(0.0, unit_cost_usd), total_cost_usd=total,
            metadata_json=metadata_json or {},
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def _spend(self, portfolio_id: uuid.UUID, *, since: datetime, until: datetime | None = None) -> float:
        stmt = select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
            CostEvent.portfolio_id == portfolio_id,
            CostEvent.created_at >= since,
        )
        if until:
            stmt = stmt.where(CostEvent.created_at < until)
        return float(await self.db.scalar(stmt) or 0)

    async def overview(self, owner_id: str = "local-user") -> dict:
        portfolio = await self.ensure(owner_id)
        now = _utcnow()
        month_start = datetime(now.year, now.month, 1)
        day_start = datetime(now.year, now.month, now.day)
        monthly_spend = await self._spend(portfolio.id, since=month_start)
        daily_spend = await self._spend(portfolio.id, since=day_start)

        channel_rows = (await self.db.execute(
            select(PortfolioChannel, Channel)
            .join(Channel, Channel.id == PortfolioChannel.channel_id)
            .where(PortfolioChannel.portfolio_id == portfolio.id, PortfolioChannel.active.is_(True))
            .order_by(Channel.created_at.asc())
        )).all()
        channels = []
        for link, channel in channel_rows:
            channel_spend = await self._spend(portfolio.id, since=month_start)
            channel_spend = float(await self.db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id,
                CostEvent.channel_id == channel.id,
                CostEvent.created_at >= month_start,
            )) or 0)
            channels.append({
                "id": str(channel.id), "name": channel.name, "youtube_channel_id": channel.youtube_channel_id,
                "budget_weight": link.budget_weight, "monthly_budget_usd": link.monthly_budget_usd,
                "monthly_spend_usd": round(channel_spend, 6),
            })

        providers = []
        provider_rows = (await self.db.execute(
            select(ProviderBudget).where(ProviderBudget.portfolio_id == portfolio.id).order_by(ProviderBudget.provider.asc())
        )).scalars().all()
        for budget in provider_rows:
            monthly = float(await self.db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id, CostEvent.provider == budget.provider,
                CostEvent.service == budget.service, CostEvent.created_at >= month_start,
            )) or 0)
            daily = float(await self.db.scalar(select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id, CostEvent.provider == budget.provider,
                CostEvent.service == budget.service, CostEvent.created_at >= day_start,
            )) or 0)
            providers.append({
                "provider": budget.provider, "service": budget.service,
                "monthly": budget_status(spent_usd=monthly, limit_usd=budget.monthly_limit_usd, hard_limit=budget.hard_limit),
                "daily": budget_status(spent_usd=daily, limit_usd=budget.daily_limit_usd, hard_limit=budget.hard_limit),
                "hard_limit": budget.hard_limit,
            })

        project_rows = (await self.db.execute(
            select(CostEvent.project_id, func.sum(CostEvent.total_cost_usd))
            .where(CostEvent.portfolio_id == portfolio.id, CostEvent.project_id.is_not(None), CostEvent.created_at >= month_start)
            .group_by(CostEvent.project_id).order_by(func.sum(CostEvent.total_cost_usd).desc()).limit(20)
        )).all()
        return {
            "portfolio": {
                "id": str(portfolio.id), "owner_id": portfolio.owner_id, "name": portfolio.name,
                "currency": portfolio.currency, "monthly_budget_usd": portfolio.monthly_budget_usd,
                "daily_budget_usd": portfolio.daily_budget_usd, "status": portfolio.status,
            },
            "spend": {
                "monthly": budget_status(spent_usd=monthly_spend, limit_usd=portfolio.monthly_budget_usd, hard_limit=False),
                "daily": budget_status(spent_usd=daily_spend, limit_usd=portfolio.daily_budget_usd, hard_limit=False),
            },
            "channels": channels,
            "providers": providers,
            "top_projects_by_cost": [{"project_id": str(pid), "monthly_cost_usd": round(float(cost or 0), 6)} for pid, cost in project_rows],
            "generated_at": now.isoformat(),
        }
