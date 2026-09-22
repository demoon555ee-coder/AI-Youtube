from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class OpportunityAnalysisRun(Base):
    __tablename__ = "opportunity_analysis_runs"
    __table_args__ = (
        Index("ix_opportunity_analysis_runs_channel_created", "channel_id", "created_at"),
        Index("ix_opportunity_analysis_runs_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    goal: Mapped[str] = mapped_column(String(30), default="balanced")
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    opportunity_count: Mapped[int] = mapped_column(Integer, default=0)
    actionable_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class OpportunityDecision(Base):
    __tablename__ = "opportunity_decisions"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "opportunity_id", name="uq_opportunity_decision_run_opp"),
        Index("ix_opportunity_decisions_channel_created", "channel_id", "created_at"),
        Index("ix_opportunity_decisions_channel_score", "channel_id", "priority_score"),
        Index("ix_opportunity_decisions_run", "analysis_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("opportunity_analysis_runs.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_opportunities.id", ondelete="CASCADE"), index=True)
    trend_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trend_events.id", ondelete="SET NULL"), nullable=True, index=True)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    base_score: Mapped[float] = mapped_column(Float, default=0.0)
    trend_boost: Mapped[float] = mapped_column(Float, default=0.0)
    urgency: Mapped[float] = mapped_column(Float, default=0.0)
    recommended_format: Mapped[str] = mapped_column(String(50), default="explainer")
    recommended_hook: Mapped[str] = mapped_column(String(50), default="question")
    recommended_duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    action: Mapped[str] = mapped_column(String(40), default="EXPLORE")
    status: Mapped[str] = mapped_column(String(30), default="ACTIONABLE")
    rationale: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
