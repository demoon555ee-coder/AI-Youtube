from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AgentGovernancePolicy(Base):
    __tablename__ = "agent_governance_policies"
    __table_args__ = (UniqueConstraint("channel_id", name="uq_agent_governance_channel"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    emergency_kill_switch: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    default_mode: Mapped[str] = mapped_column(String(20), default="approve")
    approval_timeout_minutes: Mapped[int] = mapped_column(Integer, default=120)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    automation_policies: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentActionPolicy(Base):
    __tablename__ = "agent_action_policies"
    __table_args__ = (
        UniqueConstraint("governance_policy_id", "action_type", name="uq_agent_action_policy_action"),
        Index("ix_agent_action_policy_type", "action_type", "enabled"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    governance_policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_governance_policies.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(60))
    risk_tier: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    automation_mode: Mapped[str] = mapped_column(String(20), default="approve")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    require_human_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    max_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.60)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentApprovalRequest(Base):
    __tablename__ = "agent_approval_requests"
    __table_args__ = (
        Index("ix_agent_approval_channel_status", "channel_id", "status"),
        Index("ix_agent_approval_run_status", "execution_run_id", "status"),
        Index("ix_agent_approval_task_status", "agent_task_id", "status"),
        CheckConstraint("(execution_run_id IS NOT NULL) <> (agent_task_id IS NOT NULL)", name="ck_agent_approval_exactly_one_target"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED', 'SUPERSEDED')", name="ck_agent_approval_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    execution_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("autonomous_execution_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class AgentGovernanceEvent(Base):
    __tablename__ = "agent_governance_events"
    __table_args__ = (
        Index("ix_agent_governance_event_channel_created", "channel_id", "created_at"),
        Index("ix_agent_governance_event_run_created", "execution_run_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    execution_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("autonomous_execution_runs.id", ondelete="SET NULL"), nullable=True)
    agent_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("autonomous_optimization_decisions.id", ondelete="SET NULL"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(60))
    risk_tier: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(50))
    allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_mode: Mapped[str] = mapped_column(String(20))
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    evaluation: Mapped[dict] = mapped_column(JSONB, default=dict)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
