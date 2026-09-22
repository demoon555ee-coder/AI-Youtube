from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ResearchSnapshot(Base):
    __tablename__ = "research_snapshots"
    __table_args__ = (
        Index("ix_research_snapshots_channel_query_time", "channel_id", "query", "captured_at"),
        Index("ix_research_snapshots_channel_run", "channel_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_schedules.id", ondelete="SET NULL"), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(80), default="mock")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_views: Mapped[float] = mapped_column(Float, default=0.0)
    max_views: Mapped[float] = mapped_column(Float, default=0.0)
    unique_channels: Mapped[int] = mapped_column(Integer, default=0)
    topics_json: Mapped[list] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class TrendEvent(Base):
    __tablename__ = "trend_events"
    __table_args__ = (
        UniqueConstraint("channel_id", "snapshot_id", "topic_key", "event_type", name="uq_trend_event_snapshot_topic_type"),
        Index("ix_trend_events_channel_created", "channel_id", "created_at"),
        Index("ix_trend_events_channel_type", "channel_id", "event_type"),
        Index("ix_trend_events_channel_topic", "channel_id", "topic_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_snapshots.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    topic_key: Mapped[str] = mapped_column(String(120))
    topic_label: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(40))
    current_signal: Mapped[float] = mapped_column(Float, default=0.0)
    previous_signal: Mapped[float] = mapped_column(Float, default=0.0)
    delta_signal: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
