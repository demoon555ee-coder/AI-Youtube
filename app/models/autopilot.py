from __future__ import annotations
import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ContentPlan(Base):
    __tablename__ = "content_plans"
    __table_args__ = (
        Index("ix_content_plans_channel_status", "channel_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    goal: Mapped[str] = mapped_column(String(30), default="balanced")
    cadence_per_week: Mapped[int] = mapped_column(Integer, default=3)
    publish_time: Mapped[str] = mapped_column(String(5), default="18:00")
    weekdays: Mapped[list] = mapped_column(JSONB, default=list)
    production_lead_hours: Mapped[int] = mapped_column(Integer, default=24)
    auto_publish: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentPlanItem(Base):
    __tablename__ = "content_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "position", name="uq_content_plan_item_position"),
        Index("ix_content_plan_items_due", "status", "production_start_at"),
        Index("ix_content_plan_items_plan_schedule", "plan_id", "scheduled_for"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("content_plans.id", ondelete="CASCADE"), index=True)
    idea_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("content_ideas.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("video_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    hook: Mapped[str] = mapped_column(Text, default="")
    angle: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(50), default="long_form")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime)
    production_start_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="PLANNED", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
