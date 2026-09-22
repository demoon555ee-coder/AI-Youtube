from __future__ import annotations
import uuid
from datetime import date, datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Channel, ContentPlan, ContentPlanItem
from app.models.portfolio import Portfolio, PortfolioChannel, CostEvent
from app.models.portfolio_manager import BudgetReservation, PortfolioAllocation, PortfolioDecision, PortfolioPolicy
from app.portfolio.allocation import AllocationInput, allocate_weighted_budget, dispatch_score


class PortfolioManager:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _portfolio(self, owner_id: str) -> Portfolio:
        from app.portfolio.service import PortfolioService
        return await PortfolioService(self.db).ensure(owner_id)

    async def policy(self, owner_id: str = "local-user") -> PortfolioPolicy:
        portfolio = await self._portfolio(owner_id)
        row = await self.db.scalar(select(PortfolioPolicy).where(PortfolioPolicy.portfolio_id == portfolio.id))
        if row:
            return row
        row = PortfolioPolicy(portfolio_id=portfolio.id)
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def configure_policy(self, owner_id: str, **values) -> PortfolioPolicy:
        row = await self.policy(owner_id)
        for key, value in values.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        row.planning_horizon_days = min(365, max(1, int(row.planning_horizon_days)))
        row.reserve_ratio = min(0.95, max(0.0, float(row.reserve_ratio)))
        row.target_utilization_pct = min(100.0, max(1.0, float(row.target_utilization_pct)))
        row.max_channel_concentration_pct = min(100.0, max(1.0, float(row.max_channel_concentration_pct)))
        row.min_channel_allocation_usd = max(0.0, float(row.min_channel_allocation_usd))
        row.min_daily_buffer_usd = max(0.0, float(row.min_daily_buffer_usd))
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def _spend(self, portfolio_id: uuid.UUID, *, since: datetime, channel_id=None) -> float:
        stmt = select(func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
            CostEvent.portfolio_id == portfolio_id, CostEvent.created_at >= since,
        )
        if channel_id:
            stmt = stmt.where(CostEvent.channel_id == channel_id)
        return float(await self.db.scalar(stmt) or 0.0)

    async def rebalance(self, owner_id: str = "local-user", *, allocation_date: date | None = None) -> list[PortfolioAllocation]:
        portfolio = await self._portfolio(owner_id)
        policy = await self.policy(owner_id)
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        monthly_spend = await self._spend(portfolio.id, since=month_start)
        if portfolio.monthly_budget_usd > 0:
            usable_budget = max(0.0, portfolio.monthly_budget_usd * policy.target_utilization_pct / 100.0 - monthly_spend)
        else:
            usable_budget = 0.0

        links = (await self.db.execute(
            select(PortfolioChannel, Channel).join(Channel, Channel.id == PortfolioChannel.channel_id).where(
                PortfolioChannel.portfolio_id == portfolio.id, PortfolioChannel.active.is_(True)
            ).order_by(Channel.created_at.asc())
        )).all()
        if not links:
            return []
        month_spend_rows = await self.db.execute(
            select(CostEvent.channel_id, func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id, CostEvent.created_at >= month_start
            ).group_by(CostEvent.channel_id)
        )
        spend_by_channel = {cid: float(spend or 0.0) for cid, spend in month_spend_rows.all()}
        inputs = []
        for link, channel in links:
            cap = link.monthly_budget_usd if link.monthly_budget_usd > 0 else None
            remaining_cap = max(0.0, cap - spend_by_channel.get(channel.id, 0.0)) if cap else None
            inputs.append(AllocationInput(str(channel.id), max(0.1, link.budget_weight), remaining_cap, policy.min_channel_allocation_usd))
        allocations = allocate_weighted_budget(
            usable_budget, inputs, reserve_ratio=policy.reserve_ratio, max_concentration_pct=policy.max_channel_concentration_pct
        )
        target_date = allocation_date or now.date()
        result: list[PortfolioAllocation] = []
        ranked = sorted(allocations.items(), key=lambda kv: kv[1], reverse=True)
        rank_by_channel = {cid: idx + 1 for idx, (cid, _) in enumerate(ranked)}
        for link, channel in links:
            amount = allocations.get(str(channel.id), 0.0)
            existing = await self.db.scalar(select(PortfolioAllocation).where(
                PortfolioAllocation.portfolio_id == portfolio.id,
                PortfolioAllocation.channel_id == channel.id,
                PortfolioAllocation.allocation_date == target_date,
            ).with_for_update())
            if not existing:
                existing = PortfolioAllocation(portfolio_id=portfolio.id, channel_id=channel.id, allocation_date=target_date)
                self.db.add(existing)
            existing.target_budget_usd = amount
            existing.projected_spend_usd = spend_by_channel.get(channel.id, 0.0) + amount
            existing.budget_weight = max(0.1, link.budget_weight)
            existing.fairness_score = amount / max(0.1, spend_by_channel.get(channel.id, 0.0) or 0.1)
            existing.rank = rank_by_channel.get(str(channel.id), 0)
            existing.status = "PLANNED"
            existing.metadata_json = {"monthly_spend_usd": spend_by_channel.get(channel.id, 0.0), "usable_portfolio_budget_usd": usable_budget}
            result.append(existing)
        decision = PortfolioDecision(
            portfolio_id=portfolio.id, decision_type="rebalance", action="allocate",
            reason="Weighted monthly allocation under target portfolio utilization and channel concentration caps.",
            score=usable_budget, payload={"monthly_spend_usd": monthly_spend, "usable_budget_usd": usable_budget, "channels": {str(k): v for k, v in allocations.items()}},
        )
        self.db.add(decision)
        await self.db.commit()
        for row in result:
            await self.db.refresh(row)
        return result

    async def queue_snapshot(self, owner_id: str = "local-user", limit: int = 100) -> dict:
        portfolio = await self._portfolio(owner_id)
        now = datetime.utcnow()
        rows = (await self.db.execute(
            select(ContentPlanItem, ContentPlan, Channel)
            .join(ContentPlan, ContentPlan.id == ContentPlanItem.plan_id)
            .join(Channel, Channel.id == ContentPlan.channel_id)
            .where(
                Channel.owner_id == owner_id,
                ContentPlan.status == "ACTIVE",
                ContentPlanItem.status.in_({"PLANNED", "MATERIALIZED", "ENQUEUING", "QUEUED"}),
            ).order_by(ContentPlanItem.production_start_at.asc()).limit(limit)
        )).all()
        month_start = datetime(now.year, now.month, 1)
        spend_rows = await self.db.execute(
            select(CostEvent.channel_id, func.coalesce(func.sum(CostEvent.total_cost_usd), 0)).where(
                CostEvent.portfolio_id == portfolio.id, CostEvent.created_at >= month_start
            ).group_by(CostEvent.channel_id)
        )
        spend = {cid: float(value or 0.0) for cid, value in spend_rows.all()}
        links = await self.db.execute(select(PortfolioChannel).where(PortfolioChannel.portfolio_id == portfolio.id, PortfolioChannel.active.is_(True)))
        weights = {row.channel_id: max(0.1, row.budget_weight) for row in links.scalars().all()}
        snapshot = []
        for item, plan, channel in rows:
            due_seconds = (item.production_start_at - now).total_seconds()
            ratio = spend.get(channel.id, 0.0)
            score = dispatch_score(due_at_seconds=max(0.0, -due_seconds), spend_ratio=max(0.1, ratio), budget_weight=weights.get(channel.id, 1.0))
            snapshot.append({
                "item_id": str(item.id), "project_id": str(item.project_id) if item.project_id else None,
                "channel_id": str(channel.id), "channel_name": channel.name, "title": item.title,
                "status": item.status, "production_start_at": item.production_start_at.isoformat(),
                "scheduled_for": item.scheduled_for.isoformat(), "dispatch_score": score,
            })
        snapshot.sort(key=lambda row: (-row["dispatch_score"], row["production_start_at"], row["channel_id"]))
        return {"items": snapshot[:limit], "generated_at": now.isoformat()}

    async def reserve(self, owner_id: str, *, amount_usd: float, idempotency_key: str, channel_id=None, project_id=None, purpose="production", ttl_minutes: int = 60) -> BudgetReservation:
        portfolio = await self._portfolio(owner_id)
        amount = max(0.0, float(amount_usd))
        existing = await self.db.scalar(select(BudgetReservation).where(
            BudgetReservation.portfolio_id == portfolio.id, BudgetReservation.idempotency_key == idempotency_key,
        ).with_for_update())
        if existing:
            return existing
        now = datetime.utcnow()
        if portfolio.monthly_budget_usd > 0:
            month_spend = await self._spend(portfolio.id, since=datetime(now.year, now.month, 1))
            active_reserved = float(await self.db.scalar(select(func.coalesce(func.sum(BudgetReservation.amount_usd), 0)).where(
                BudgetReservation.portfolio_id == portfolio.id, BudgetReservation.status == "ACTIVE", BudgetReservation.expires_at > now
            )) or 0.0)
            if month_spend + active_reserved + amount > portfolio.monthly_budget_usd:
                raise ValueError("Portfolio budget reservation would exceed monthly budget")
        row = BudgetReservation(portfolio_id=portfolio.id, channel_id=channel_id, project_id=project_id,
                                amount_usd=amount, purpose=purpose, idempotency_key=idempotency_key,
                                expires_at=now + timedelta(minutes=max(1, ttl_minutes)))
        self.db.add(row)
        self.db.add(PortfolioDecision(
            portfolio_id=portfolio.id, decision_type="reservation", action="reserve",
            reason="Budget reserved before production execution.", score=amount,
            payload={"amount_usd": amount, "purpose": purpose, "idempotency_key": idempotency_key},
        ))
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def release(self, owner_id: str, reservation_id: str) -> BudgetReservation:
        portfolio = await self._portfolio(owner_id)
        row = await self.db.scalar(select(BudgetReservation).where(
            BudgetReservation.id == uuid.UUID(reservation_id), BudgetReservation.portfolio_id == portfolio.id
        ).with_for_update())
        if not row:
            raise ValueError("Reservation not found")
        if row.status == "ACTIVE":
            row.status = "RELEASED"
            row.released_at = datetime.utcnow()
            await self.db.commit()
        return row

    async def release_expired(self, owner_id: str = "local-user") -> int:
        portfolio = await self._portfolio(owner_id)
        now = datetime.utcnow()
        rows = await self.db.execute(select(BudgetReservation).where(
            BudgetReservation.portfolio_id == portfolio.id,
            BudgetReservation.status == "ACTIVE",
            BudgetReservation.expires_at <= now,
        ).with_for_update(skip_locked=True))
        count = 0
        for row in rows.scalars().all():
            row.status = "EXPIRED"
            row.released_at = now
            count += 1
        if count:
            self.db.add(PortfolioDecision(
                portfolio_id=portfolio.id, decision_type="reservation", action="expire",
                reason="Expired budget reservations were released.", score=count, payload={"count": count},
            ))
            await self.db.commit()
        return count

    async def forecast(self, owner_id: str = "local-user", *, days: int = 30, average_video_cost_usd: float = 1.0) -> dict:
        if days < 1 or days > 365:
            raise ValueError("days must be between 1 and 365")
        portfolio = await self._portfolio(owner_id)
        rows = (await self.db.execute(select(ContentPlanItem, ContentPlan, Channel).join(ContentPlan, ContentPlan.id == ContentPlanItem.plan_id).join(Channel, Channel.id == ContentPlan.channel_id).where(
            Channel.owner_id == owner_id, ContentPlan.status == "ACTIVE",
            ContentPlanItem.scheduled_for >= datetime.utcnow(),
            ContentPlanItem.scheduled_for < datetime.utcnow() + timedelta(days=days),
            ContentPlanItem.status.in_({"PLANNED", "MATERIALIZED", "ENQUEUING", "QUEUED"}),
        ))).all()
        estimated_videos = len(rows)
        estimated_cost = round(estimated_videos * max(0.0, average_video_cost_usd), 8)
        now = datetime.utcnow()
        month_spend = await self._spend(portfolio.id, since=datetime(now.year, now.month, 1))
        budget = portfolio.monthly_budget_usd
        return {
            "days": days, "scheduled_videos": estimated_videos,
            "average_video_cost_usd": max(0.0, average_video_cost_usd),
            "projected_production_cost_usd": estimated_cost,
            "current_month_spend_usd": month_spend,
            "projected_month_spend_usd": round(month_spend + estimated_cost, 8),
            "monthly_budget_usd": budget,
            "within_budget": bool(budget <= 0 or month_spend + estimated_cost <= budget),
        }
