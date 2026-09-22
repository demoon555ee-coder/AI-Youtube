from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ResearchSchedule(Base):
    __tablename__ = "research_schedules"
    __table_args__ = (
        UniqueConstraint("channel_id", "name", name="uq_research_schedule_channel_name"),
        Index("ix_research_schedules_due", "enabled", "next_run_at", "locked_until"),
        Index("ix_research_schedules_channel", "channel_id", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cadence_hours: Mapped[float] = mapped_column(Float, default=24.0)
    next_run_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_results: Mapped[int] = mapped_column(Integer, default=10)
    published_after_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_generate_ideas: Mapped[bool] = mapped_column(Boolean, default=False)
    idea_count: Mapped[int] = mapped_column(Integer, default=5)
    goal: Mapped[str] = mapped_column(String(30), default="balanced")
    catch_up: Mapped[bool] = mapped_column(Boolean, default=False)
    max_runs_per_day: Mapped[int] = mapped_column(Integer, default=3)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(30), default="NEVER_RUN")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchRun(Base):
    __tablename__ = "research_runs"
    __table_args__ = (
        Index("ix_research_runs_schedule_started", "schedule_id", "started_at"),
        Index("ix_research_runs_channel_started", "channel_id", "started_at"),
        Index("ix_research_runs_status", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_schedules.id", ondelete="CASCADE"), index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(80), default="mock")
    trigger_type: Mapped[str] = mapped_column(String(30), default="scheduled")
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    opportunity_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_idea_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
