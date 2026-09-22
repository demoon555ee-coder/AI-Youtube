from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Channel, ContentIdea, ResearchOpportunity
from app.content.service import load_channel_memory
from app.content.strategy import ContentStrategyEngine


async def generate_from_opportunities(db: AsyncSession, *, channel_id: str, opportunity_ids: list[str], count: int, goal: str) -> list[ContentIdea]:
    channel = await db.get(Channel, uuid.UUID(channel_id))
    if not channel:
        raise ValueError("Channel not found")
    ids = [uuid.UUID(x) for x in opportunity_ids]
    q = await db.execute(select(ResearchOpportunity).where(
        ResearchOpportunity.channel_id == channel.id,
        ResearchOpportunity.id.in_(ids),
    ).order_by(ResearchOpportunity.score.desc()))
    opportunities = list(q.scalars().all())
    if not opportunities:
        raise ValueError("No research opportunities found for this channel")
    memory = await load_channel_memory(db, channel_id)
    engine = ContentStrategyEngine()
    seeds = [x.topic for x in opportunities]
    candidates = engine.generate(
        channel={"name": channel.name, "niche": channel.niche, "language": channel.language},
        memory=memory,
        seed_topics=seeds,
        count=max(1, min(count, 50)),
        goal=goal,
    )
    created = []
    for index, candidate in enumerate(candidates):
        opportunity = opportunities[index % len(opportunities)]
        rationale = dict(candidate.rationale)
        rationale["research_opportunity"] = {
            "id": str(opportunity.id),
            "score": opportunity.score,
            "demand_signal": opportunity.demand_signal,
            "competition_signal": opportunity.competition_signal,
            "freshness_signal": opportunity.freshness_signal,
            "gap_signal": opportunity.gap_signal,
        }
        row = ContentIdea(
            channel_id=channel.id,
            research_opportunity_id=opportunity.id,
            topic=candidate.topic,
            title=candidate.title,
            hook=candidate.hook,
            angle=candidate.angle,
            language=channel.language,
            target_duration_minutes=candidate.duration_minutes,
            demand_signal=candidate.demand_signal,
            competition_signal=candidate.competition_signal,
            channel_fit=candidate.channel_fit,
            novelty=candidate.novelty,
            production_cost=candidate.production_cost,
            composite_score=candidate.composite_score,
            rationale=rationale,
        )
        db.add(row)
        created.append(row)
    await db.commit()
    for row in created:
        await db.refresh(row)
    return created
