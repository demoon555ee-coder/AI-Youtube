import uuid
from datetime import datetime
from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class ChannelMemory(Base):
    __tablename__ = "channel_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True)
    version: Mapped[int] = mapped_column(default=1)
    summary: Mapped[str] = mapped_column(Text, default="")
    learned_patterns: Mapped[list] = mapped_column(JSON, default=list)
    topic_clusters: Mapped[list] = mapped_column(JSON, default=list)
    hook_patterns: Mapped[list] = mapped_column(JSON, default=list)
    title_patterns: Mapped[list] = mapped_column(JSON, default=list)
    pacing_patterns: Mapped[list] = mapped_column(JSON, default=list)
    production_notes: Mapped[list] = mapped_column(JSON, default=list)
    source_video_count: Mapped[int] = mapped_column(default=0)
    last_analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
