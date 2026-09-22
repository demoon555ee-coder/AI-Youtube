from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ProviderProfile(Base):
    __tablename__ = "provider_profiles"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "provider", "service", name="uq_provider_profile"),
        Index("ix_provider_profiles_portfolio_service", "portfolio_id", "service", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(100))
    service: Mapped[str] = mapped_column(String(100), default="llm")
    kind: Mapped[str] = mapped_column(String(100), default="mock")
    quality_tier: Mapped[str] = mapped_column(String(30), default="standard")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    unit: Mapped[str] = mapped_column(String(50), default="request")
    unit_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    capabilities: Mapped[dict] = mapped_column(JSONB, default=dict)
    config_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"
    __table_args__ = (
        Index("ix_routing_decisions_project_created", "project_id", "created_at"),
        Index("ix_routing_decisions_portfolio_created", "portfolio_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(120), default="local-user", index=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("video_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    step_name: Mapped[str] = mapped_column(String(100))
    service: Mapped[str] = mapped_column(String(100))
    requested_tier: Mapped[str] = mapped_column(String(30), default="standard")
    chosen_provider: Mapped[str] = mapped_column(String(100))
    chosen_tier: Mapped[str] = mapped_column(String(30), default="standard")
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(500), default="")
    candidates_json: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
