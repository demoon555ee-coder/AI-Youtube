from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.channel import Channel
from app.models.channel_memory import ChannelMemory
from app.models.content import ContentIdea, ContentStrategySnapshot
from app.content.strategy import ContentStrategyEngine


async def load_channel_memory(db: AsyncSession, channel_id: str) -> dict:
    q = await db.execute(select(ChannelMemory).where(ChannelMemory.channel_id == uuid.UUID(channel_id)))
    memory = q.scalar_one_or_none()
    if not memory:
        return {"version": 0, "learned_patterns": [], "topic_clusters": [], "hook_patterns": [], "title_patterns": [], "pacing_patterns": []}
    return {
        "version": memory.version,
        "summary": memory.summary,
        "learned_patterns": memory.learned_patterns or [],
        "topic_clusters": memory.topic_clusters or [],
        "hook_patterns": memory.hook_patterns or [],
        "title_patterns": memory.title_patterns or [],
        "pacing_patterns": memory.pacing_patterns or [],
    }


async def generate_ideas(
    db: AsyncSession,
    *,
    channel_id: str,
    seed_topics: list[str],
    count: int,
    goal: str,
) -> dict:
    channel = await db.get(Channel, uuid.UUID(channel_id))
    if not channel:
        raise ValueError("Channel not found")

    memory = await load_channel_memory(db, channel_id)
    engine = ContentStrategyEngine()
    strategy = engine.build_strategy(
        channel={"name": channel.name, "niche": channel.niche, "language": channel.language},
        memory=memory,
        goal=goal,
    )
    ideas = engine.generate(
        channel={"name": channel.name, "niche": channel.niche, "language": channel.language},
        memory=memory,
        seed_topics=seed_topics,
        count=count,
        goal=goal,
    )

    snapshot = ContentStrategySnapshot(channel_id=channel.id, goal=goal, strategy=strategy)
    db.add(snapshot)
    for idea in ideas:
        db.add(ContentIdea(
            channel_id=channel.id,
            topic=idea.topic,
            title=idea.title,
            hook=idea.hook,
            angle=idea.angle,
            language=channel.language,
            target_duration_minutes=idea.duration_minutes,
            demand_signal=idea.demand_signal,
            competition_signal=idea.competition_signal,
            channel_fit=idea.channel_fit,
            novelty=idea.novelty,
            production_cost=idea.production_cost,
            composite_score=idea.composite_score,
            rationale=idea.rationale,
        ))
    await db.commit()
    return {
        "channel_id": channel_id,
        "strategy": strategy,
        "ideas": [
            {
                "topic": x.topic,
                "title": x.title,
                "hook": x.hook,
                "angle": x.angle,
                "duration_minutes": x.duration_minutes,
                "demand_signal": x.demand_signal,
                "competition_signal": x.competition_signal,
                "channel_fit": x.channel_fit,
                "novelty": x.novelty,
                "production_cost": x.production_cost,
                "composite_score": x.composite_score,
                "rationale": x.rationale,
            } for x in ideas
        ],
    }


async def list_ideas(db: AsyncSession, channel_id: str, limit: int = 50) -> list[ContentIdea]:
    q = await db.execute(
        select(ContentIdea)
        .where(ContentIdea.channel_id == uuid.UUID(channel_id))
        .order_by(ContentIdea.composite_score.desc(), ContentIdea.created_at.desc())
        .limit(limit)
    )
    return list(q.scalars().all())


async def select_idea(db: AsyncSession, channel_id: str, idea_id: str) -> ContentIdea:
    idea = await db.get(ContentIdea, uuid.UUID(idea_id))
    if not idea or idea.channel_id != uuid.UUID(channel_id):
        raise ValueError("Idea not found")
    q = await db.execute(select(ContentIdea).where(ContentIdea.channel_id == uuid.UUID(channel_id)))
    for other in q.scalars().all():
        other.selected = False
    idea.selected = True
    idea.status = "SELECTED"
    await db.commit()
    return idea


async def create_project_from_selected_idea(db: AsyncSession, channel_id: str, idea_id: str):
    from app.models.domain import VideoProject
    idea = await db.get(ContentIdea, uuid.UUID(idea_id))
    if not idea or idea.channel_id != uuid.UUID(channel_id):
        raise ValueError("Idea not found")
    if not idea.selected:
        raise ValueError("Idea must be selected before creating a project")
    from app.content.intelligence import ContentIntelligenceEngine
    from app.models.intelligence import ContentBlueprint
    memory = await load_channel_memory(db, channel_id)
    channel = await db.get(Channel, idea.channel_id)
    engine = ContentIntelligenceEngine()
    blueprint_spec = engine.build_blueprint(
        channel={"name": channel.name, "niche": channel.niche, "language": channel.language},
        memory=memory,
        idea={"topic": idea.topic, "title": idea.title, "hook": idea.hook, "angle": idea.angle},
        goal=str((idea.rationale or {}).get("goal") or "balanced"),
    )
    project = VideoProject(channel_id=idea.channel_id, topic=idea.topic, data={
        "idea_id": str(idea.id),
        "title": idea.title,
        "hook": idea.hook,
        "angle": idea.angle,
        "strategy": idea.rationale,
        "content_intelligence": {
            "format": blueprint_spec.format,
            "hook_pattern": blueprint_spec.hook_pattern,
            "target_duration_minutes": blueprint_spec.target_duration_minutes,
            "visual_change_seconds": blueprint_spec.visual_change_seconds,
            "narrative_structure": blueprint_spec.narrative_structure,
            "packaging": blueprint_spec.packaging,
            "experiment_spec": blueprint_spec.experiment_spec,
            "confidence": blueprint_spec.confidence,
        },
    })
    db.add(project)
    await db.flush()
    db.add(ContentBlueprint(
        channel_id=idea.channel_id,
        idea_id=idea.id,
        project_id=project.id,
        format=blueprint_spec.format,
        hook_pattern=blueprint_spec.hook_pattern,
        target_duration_minutes=blueprint_spec.target_duration_minutes,
        visual_change_seconds=blueprint_spec.visual_change_seconds,
        narrative_structure={"sections": blueprint_spec.narrative_structure},
        packaging=blueprint_spec.packaging,
        experiment_spec=blueprint_spec.experiment_spec,
        reasoning=blueprint_spec.reasoning,
        confidence=blueprint_spec.confidence,
    ))
    idea.status = "CONVERTED_TO_PROJECT"
    await db.commit()
    await db.refresh(project)
    return project
