from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import AnalyticsSnapshot
from app.models.channel_memory import ChannelMemory
from app.models.optimization import OptimizationReport
from app.models.publication import Publication
from app.brain.analyzer import ChannelBrainAnalyzer, VideoMetricRow


def _row_to_metric(row: AnalyticsSnapshot) -> VideoMetricRow:
    return VideoMetricRow(
        video_id=row.youtube_video_id or "",
        views=row.views,
        watch_time_minutes=row.watch_time_minutes,
        avg_view_duration=row.average_view_duration,
        avg_view_percentage=row.average_view_percentage,
        likes=row.likes,
        comments=row.comments,
        shares=row.shares,
        subscribers_gained=row.subscribers_gained,
        subscribers_lost=row.subscribers_lost,
    )


async def get_or_create_memory(db: AsyncSession, channel_id: str) -> ChannelMemory:
    cid = uuid.UUID(channel_id)
    q = await db.execute(select(ChannelMemory).where(ChannelMemory.channel_id == cid))
    memory = q.scalar_one_or_none()
    if memory:
        return memory
    memory = ChannelMemory(channel_id=cid)
    db.add(memory)
    await db.flush()
    return memory


async def rebuild_memory(db: AsyncSession, channel_id: str, min_video_count: int = 3) -> dict:
    cid = uuid.UUID(channel_id)
    q = await db.execute(
        select(AnalyticsSnapshot)
        .where(AnalyticsSnapshot.channel_id == cid, AnalyticsSnapshot.youtube_video_id.is_not(None))
        .order_by(AnalyticsSnapshot.day.desc())
    )
    snapshots = list(q.scalars().all())

    latest_by_video: dict[str, AnalyticsSnapshot] = {}
    for snapshot in snapshots:
        latest_by_video.setdefault(snapshot.youtube_video_id or "", snapshot)
    rows = [_row_to_metric(r) for r in latest_by_video.values() if r.youtube_video_id]

    if len(rows) < min_video_count:
        raise RuntimeError(f"Need at least {min_video_count} analyzed videos; only {len(rows)} found")

    brain = ChannelBrainAnalyzer()
    result = brain.analyze_channel(rows)
    memory = await get_or_create_memory(db, channel_id)
    memory.version += 1 if memory.source_video_count else 0
    memory.summary = result["summary"]
    prior_experiment_patterns = [
        pattern for pattern in (memory.learned_patterns or [])
        if isinstance(pattern, dict) and pattern.get("type") == "experiment_signal"
    ]
    memory.learned_patterns = result["learned_patterns"] + prior_experiment_patterns[-20:]
    memory.topic_clusters = result["topic_clusters"]
    memory.hook_patterns = result["hook_patterns"]
    memory.title_patterns = result["title_patterns"]
    memory.pacing_patterns = result["pacing_patterns"]
    memory.production_notes = result["production_notes"]
    memory.source_video_count = len(rows)
    memory.last_analyzed_at = datetime.utcnow()
    await db.commit()
    return {
        "channel_id": channel_id,
        "source_video_count": len(rows),
        "version": memory.version,
        **result,
    }


async def optimize_video(db: AsyncSession, channel_id: str, video_id: str) -> dict:
    cid = uuid.UUID(channel_id)
    q = await db.execute(
        select(AnalyticsSnapshot)
        .where(
            AnalyticsSnapshot.channel_id == cid,
            AnalyticsSnapshot.youtube_video_id == video_id,
        )
        .order_by(AnalyticsSnapshot.day.desc())
        .limit(1)
    )
    latest = q.scalar_one_or_none()
    if not latest:
        raise RuntimeError("No stored analytics found for this video")

    memory = await get_or_create_memory(db, channel_id)
    analyzer = ChannelBrainAnalyzer()
    result = analyzer.optimize_video(_row_to_metric(latest), {
        "learned_patterns": memory.learned_patterns,
    })

    publication_q = await db.execute(select(Publication).where(Publication.youtube_video_id == video_id).limit(1))
    publication = publication_q.scalar_one_or_none()
    report = OptimizationReport(
        channel_id=cid,
        youtube_video_id=video_id,
        video_project_id=publication.project_id if publication else None,
        diagnosis=result["diagnosis"],
        actions=result["actions"],
        hypotheses=result["hypotheses"],
        confidence=result["confidence"],
    )
    db.add(report)
    await db.commit()
    return {
        "report_id": str(report.id),
        "channel_id": channel_id,
        "youtube_video_id": video_id,
        **result,
    }


async def learn_from_experiment(db: AsyncSession, experiment_id: str) -> dict:
    from app.models.experiments import ContentExperiment
    exp = await db.get(ContentExperiment, uuid.UUID(experiment_id))
    if not exp:
        raise RuntimeError("Experiment not found")
    memory = await get_or_create_memory(db, str(exp.channel_id))
    patterns = list(memory.learned_patterns or [])
    decision = (exp.result or {}).get("decision") or {}
    pattern = {
        "type": "experiment_signal",
        "experiment_id": str(exp.id),
        "dimension": exp.dimension,
        "primary_metric": (exp.result or {}).get("primary_metric"),
        "decision_state": decision.get("state"),
        "leading_variant": decision.get("leading_variant"),
        "delta_vs_second": decision.get("delta_vs_second"),
    }
    patterns.append(pattern)
    memory.learned_patterns = patterns[-50:]
    memory.version += 1
    memory.updated_at = datetime.utcnow()
    await db.commit()
    return pattern
