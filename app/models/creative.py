from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, String, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class CreativeAnalysis(Base):
    __tablename__ = "creative_analyses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("video_projects.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(40), default="post_render")
    status: Mapped[str] = mapped_column(String(20), default="PASS", index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    sampled_frames: Mapped[int] = mapped_column(Integer, default=0)
    scene_reports: Mapped[list] = mapped_column(JSONB, default=list)
    audio_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)
    visual_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)
    issues: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    reedit_plan: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
