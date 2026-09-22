import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Float, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ContentIdea(Base):
    __tablename__ = "content_ideas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    research_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    hook: Mapped[str] = mapped_column(Text)
    angle: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    target_duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    demand_signal: Mapped[float] = mapped_column(Float, default=0)
    competition_signal: Mapped[float] = mapped_column(Float, default=0)
    channel_fit: Mapped[float] = mapped_column(Float, default=0)
    novelty: Mapped[float] = mapped_column(Float, default=0)
    production_cost: Mapped[float] = mapped_column(Float, default=0)
    composite_score: Mapped[float] = mapped_column(Float, default=0)
    rationale: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="CANDIDATE")
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentStrategySnapshot(Base):
    __tablename__ = "content_strategy_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    research_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    goal: Mapped[str] = mapped_column(String(50), default="balanced")
    strategy: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
