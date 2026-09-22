from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class PortfolioPolicy(Base):
    __tablename__ = "portfolio_policies"
    __table_args__ = (UniqueConstraint("portfolio_id", name="uq_portfolio_policy"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    planning_horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    reserve_ratio: Mapped[float] = mapped_column(Float, default=0.10)
    target_utilization_pct: Mapped[float] = mapped_column(Float, default=80.0)
    max_channel_concentration_pct: Mapped[float] = mapped_column(Float, default=50.0)
    min_channel_allocation_usd: Mapped[float] = mapped_column(Float, default=0.0)
    min_daily_buffer_usd: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(default=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PortfolioAllocation(Base):
    __tablename__ = "portfolio_allocations"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "channel_id", "allocation_date", name="uq_portfolio_allocation_day"),
        Index("ix_portfolio_allocations_portfolio_date", "portfolio_id", "allocation_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    allocation_date: Mapped[datetime] = mapped_column(Date)
    target_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    reserved_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    projected_spend_usd: Mapped[float] = mapped_column(Float, default=0.0)
    budget_weight: Mapped[float] = mapped_column(Float, default=1.0)
    fairness_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="PLANNED", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PortfolioDecision(Base):
    __tablename__ = "portfolio_decisions"
    __table_args__ = (Index("ix_portfolio_decisions_portfolio_created", "portfolio_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    decision_type: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "idempotency_key", name="uq_budget_reservation_key"),
        Index("ix_budget_reservations_portfolio_status", "portfolio_id", "status"),
        Index("ix_budget_reservations_expires", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("video_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    purpose: Mapped[str] = mapped_column(String(100), default="production")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
