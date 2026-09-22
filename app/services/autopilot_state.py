from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.autopilot import ContentPlan, ContentPlanItem
from app.models.domain import VideoProject

TERMINAL_ITEM_STATUSES = {"READY_TO_PUBLISH", "SCHEDULED", "COMPLETED", "CANCELLED"}


async def sync_plan_item_after_workflow(db: AsyncSession, project_id: uuid.UUID, status: str = "READY_TO_PUBLISH") -> None:
    project = await db.get(VideoProject, project_id)
    if not project:
        return
    data = project.data or {}
    plan_item_id = data.get("plan_item_id") or data.get("schedule", {}).get("plan_item_id")
    if not plan_item_id:
        return
    item = await db.get(ContentPlanItem, uuid.UUID(str(plan_item_id)))
    if not item:
        return
    item.status = status
    item.error_message = None
    plan = await db.get(ContentPlan, item.plan_id)
    if plan:
        q = await db.execute(select(ContentPlanItem.status).where(ContentPlanItem.plan_id == plan.id))
        states = [row[0] for row in q.all()]
        if states and all(state in TERMINAL_ITEM_STATUSES for state in states):
            plan.status = "COMPLETED"
