from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ContentBlueprint(Base):
    __tablename__ = "content_blueprints"
    __table_args__ = (
        Index("ix_content_blueprints_channel_created", "channel_id", "created_at"),
        Index("ix_content_blueprints_channel_status", "channel_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    idea_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("content_ideas.id", ondelete="SET NULL"), nullable=True, index=True)
    plan_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("content_plan_items.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("video_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    format: Mapped[str] = mapped_column(String(50), default="explainer")
    hook_pattern: Mapped[str] = mapped_column(String(50), default="question")
    target_duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    visual_change_seconds: Mapped[float] = mapped_column(Float, default=4.5)
    narrative_structure: Mapped[dict] = mapped_column(JSONB, default=dict)
    packaging: Mapped[dict] = mapped_column(JSONB, default=dict)
    experiment_spec: Mapped[dict] = mapped_column(JSONB, default=dict)
    reasoning: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
