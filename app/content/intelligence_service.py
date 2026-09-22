from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.content.service import load_channel_memory
from app.content.intelligence import ContentIntelligenceEngine
from app.models.channel import Channel
from app.models.content import ContentIdea
from app.models.autopilot import ContentPlanItem
from app.models.intelligence import ContentBlueprint


async def build_for_idea(db: AsyncSession, *, channel_id: str, idea_id: str, goal: str = "balanced", plan_item_id: str | None = None, project_id: str | None = None) -> ContentBlueprint:
    channel = await db.get(Channel, uuid.UUID(channel_id))
    idea = await db.get(ContentIdea, uuid.UUID(idea_id))
    if not channel or not idea or idea.channel_id != channel.id:
        raise ValueError("Idea not found")
    memory = await load_channel_memory(db, channel_id)
    engine = ContentIntelligenceEngine()
    spec = engine.build_blueprint(
        channel={"name": channel.name, "niche": channel.niche, "language": channel.language},
        memory=memory,
        idea={"topic": idea.topic, "title": idea.title, "hook": idea.hook, "angle": idea.angle},
        goal=goal,
    )
    blueprint = ContentBlueprint(
        channel_id=channel.id,
        idea_id=idea.id,
        plan_item_id=uuid.UUID(plan_item_id) if plan_item_id else None,
        project_id=uuid.UUID(project_id) if project_id else None,
        format=spec.format,
        hook_pattern=spec.hook_pattern,
        target_duration_minutes=spec.target_duration_minutes,
        visual_change_seconds=spec.visual_change_seconds,
        narrative_structure={"sections": spec.narrative_structure},
        packaging=spec.packaging,
        experiment_spec=spec.experiment_spec,
        reasoning=spec.reasoning,
        confidence=spec.confidence,
        status="ACTIVE",
    )
    db.add(blueprint)
    await db.commit()
    await db.refresh(blueprint)
    return blueprint


async def build_for_plan_item(db: AsyncSession, *, channel_id: str, plan_item_id: str, goal: str) -> ContentBlueprint:
    item = await db.get(ContentPlanItem, uuid.UUID(plan_item_id))
    if not item:
        raise ValueError("Plan item not found")
    if str(item.plan_id) is None:
        raise ValueError("Plan item has no plan")
    if not item.idea_id:
        raise ValueError("Plan item has no idea")
    return await build_for_idea(db, channel_id=channel_id, idea_id=str(item.idea_id), goal=goal, plan_item_id=str(item.id), project_id=str(item.project_id) if item.project_id else None)


def serialize_blueprint(row: ContentBlueprint) -> dict:
    return {
        "id": str(row.id),
        "channel_id": str(row.channel_id),
        "idea_id": str(row.idea_id) if row.idea_id else None,
        "plan_item_id": str(row.plan_item_id) if row.plan_item_id else None,
        "project_id": str(row.project_id) if row.project_id else None,
        "format": row.format,
        "hook_pattern": row.hook_pattern,
        "target_duration_minutes": row.target_duration_minutes,
        "visual_change_seconds": row.visual_change_seconds,
        "narrative_structure": row.narrative_structure or {},
        "packaging": row.packaging or {},
        "experiment_spec": row.experiment_spec or {},
        "reasoning": row.reasoning or {},
        "confidence": row.confidence,
        "status": row.status,
        "created_at": row.created_at,
    }


async def list_blueprints(db: AsyncSession, *, channel_id: str, limit: int = 50) -> list[ContentBlueprint]:
    q = await db.execute(
        select(ContentBlueprint)
        .where(ContentBlueprint.channel_id == uuid.UUID(channel_id))
        .order_by(ContentBlueprint.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    return list(q.scalars().all())
