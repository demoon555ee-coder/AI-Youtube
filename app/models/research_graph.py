from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ResearchNode(Base):
    __tablename__ = "research_nodes"
    __table_args__ = (
        UniqueConstraint("channel_id", "node_type", "external_id", name="uq_research_node_identity"),
        Index("ix_research_nodes_channel_type", "channel_id", "node_type"),
        Index("ix_research_nodes_channel_created", "channel_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    node_type: Mapped[str] = mapped_column(String(40), default="topic")
    external_id: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchEdge(Base):
    __tablename__ = "research_edges"
    __table_args__ = (
        UniqueConstraint("channel_id", "source_node_id", "target_node_id", "relation", name="uq_research_edge_identity"),
        Index("ix_research_edges_channel_relation", "channel_id", "relation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_nodes.id", ondelete="CASCADE"))
    target_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_nodes.id", ondelete="CASCADE"))
    relation: Mapped[str] = mapped_column(String(60), default="related_to")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ResearchOpportunity(Base):
    __tablename__ = "research_opportunities"
    __table_args__ = (
        Index("ix_research_opportunities_channel_score", "channel_id", "score"),
        Index("ix_research_opportunities_channel_status", "channel_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    demand_signal: Mapped[float] = mapped_column(Float, default=0.0)
    competition_signal: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_signal: Mapped[float] = mapped_column(Float, default=0.0)
    gap_signal: Mapped[float] = mapped_column(Float, default=0.0)
    channel_fit: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_node_ids: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="DISCOVERED")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
