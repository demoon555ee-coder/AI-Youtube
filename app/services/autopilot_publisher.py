from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.domain import VideoProject
from app.models.autopilot import ContentPlanItem, ContentPlan
from app.models.channel import Channel
from app.models.youtube_connection import YouTubeConnection
from app.governance.service import AgentGovernanceService


async def auto_publish_if_due(db: AsyncSession, project_id: uuid.UUID) -> bool:
    project = await db.get(VideoProject, project_id)
    if not project:
        return False
    schedule = (project.data or {}).get("schedule", {})
    if not schedule.get("auto_publish") or project.status != "READY_TO_PUBLISH":
        return False
    publish_at = schedule.get("scheduled_for")
    if not publish_at:
        return False
    channel = await db.get(Channel, project.channel_id)
    if not channel:
        return False
    from app.runtime.service import AgentRuntimeError, AgentRuntimeService
    data = project.data or {}
    script = data.get("script") or {}
    research = data.get("research") or {}
    try:
        task = await AgentRuntimeService(db).create_task(
            channel_id=channel.id, agent_key="publisher", task_type="publisher", action_type="publish",
            input_data={
                "channel_id": str(channel.id), "project_id": str(project.id),
                "title": script.get("title") or data.get("title") or project.topic,
                "description": script.get("description") or data.get("description") or "",
                "tags": research.get("keywords") or [], "category_id": str(schedule.get("category_id") or "22"),
                "privacy_status": "private", "publish_at": publish_at,
            },
            budget_usd=0.5, confidence=0.90, requested_mode="auto",
            idempotency_key=f"autopublish:{project.id}:{publish_at}", project_id=project.id,
        )
    except AgentRuntimeError:
        return False
    await db.commit()
    return task.status in {"PENDING", "PENDING_APPROVAL"}

