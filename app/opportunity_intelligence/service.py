from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.intelligence import ContentIntelligenceEngine
from app.content.service import load_channel_memory
from app.models import Channel, ResearchOpportunity, TrendEvent, OpportunityAnalysisRun, OpportunityDecision

VALID_GOALS = {"growth", "authority", "monetization", "balanced"}
EVENT_BOOST = {"NEW": 0.14, "RISING": 0.20, "FALLING": -0.14, "DISAPPEARING": -0.20}
ACTION_BY_EVENT = {
    "NEW": "EXPLORE_NOW",
    "RISING": "EXPLORE_NOW",
    "FALLING": "REFINE",
    "DISAPPEARING": "DEPRIORITIZE",
}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _tokens(text: str) -> set[str]:
    return {x for x in text.lower().replace("/", " ").replace("-", " ").split() if len(x) >= 4}


def _overlap(a: str, b: str) -> float:
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


class OpportunityIntelligenceService:
    """Turns research/trend observations into auditable prioritization decisions.

    The score is a decision heuristic, not a prediction of views or a causal claim.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.content = ContentIntelligenceEngine()

    async def analyze(self, *, channel_id: str, goal: str = "balanced", limit: int = 50, min_score: float = 0.0) -> OpportunityAnalysisRun:
        channel = await self.db.get(Channel, uuid.UUID(channel_id))
        if not channel:
            raise ValueError("Channel not found")
        goal = goal if goal in VALID_GOALS else "balanced"
        limit = max(1, min(limit, 100))
        min_score = _clamp(float(min_score))
        run = OpportunityAnalysisRun(channel_id=channel.id, goal=goal, status="RUNNING")
        self.db.add(run)
        await self.db.flush()
        try:
            q = await self.db.execute(
                select(ResearchOpportunity)
                .where(ResearchOpportunity.channel_id == channel.id)
                .order_by(ResearchOpportunity.score.desc(), ResearchOpportunity.last_seen_at.desc())
                .limit(limit)
            )
            opportunities = list(q.scalars().all())
            memory = await load_channel_memory(self.db, channel_id)
            trend_q = await self.db.execute(
                select(TrendEvent)
                .where(TrendEvent.channel_id == channel.id, TrendEvent.created_at >= datetime.utcnow() - timedelta(days=14))
                .order_by(TrendEvent.created_at.desc())
            )
            trend_events = list(trend_q.scalars().all())
            latest_by_key: dict[str, TrendEvent] = {}
            for event in trend_events:
                latest_by_key.setdefault(event.topic_key, event)

            channel_ctx = {"name": channel.name, "niche": channel.niche, "language": channel.language}
            actionable = 0
            for opp in opportunities:
                event = latest_by_key.get(self._topic_key(opp.topic)) or self._fuzzy_event(opp.topic, trend_events)
                event_boost = EVENT_BOOST.get(event.event_type, 0.0) if event else 0.0
                trend_momentum = _clamp(abs(float(event.delta_signal or 0.0)) * 1.5) if event else 0.0
                fit = _clamp(float(opp.channel_fit or 0.0))
                freshness = _clamp(float(opp.freshness_signal or 0.0))
                gap = _clamp(float(opp.gap_signal or 0.0))
                competition_inverse = 1.0 - _clamp(float(opp.competition_signal or 0.0))
                memory_fit = self._memory_fit(opp.topic, memory)
                trend_component = _clamp(0.5 + event_boost + (trend_momentum * (1 if event and event.event_type in {"NEW", "RISING"} else -1 if event else 0)))
                cost_feasibility = 1.0 - (0.15 if goal == "monetization" else 0.05)
                base = _clamp(float(opp.score or 0.0))
                score = (
                    base * 0.42
                    + trend_component * 0.22
                    + fit * 0.12
                    + gap * 0.08
                    + freshness * 0.06
                    + competition_inverse * 0.05
                    + memory_fit * 0.03
                    + cost_feasibility * 0.02
                )
                priority = _clamp(score)
                action = ACTION_BY_EVENT.get(event.event_type, "EXPLORE") if event else "EXPLORE"
                if priority < min_score:
                    action = "HOLD"
                blueprint = self.content.build_blueprint(
                    channel=channel_ctx,
                    memory=memory,
                    idea={"topic": opp.topic, "title": opp.topic, "hook": "", "angle": "future impact"},
                    goal=goal,
                )
                actionable = action in {"EXPLORE_NOW", "EXPLORE"}
                decision = OpportunityDecision(
                    analysis_run_id=run.id,
                    channel_id=channel.id,
                    opportunity_id=opp.id,
                    trend_event_id=event.id if event else None,
                    priority_score=round(priority, 6),
                    base_score=round(base, 6),
                    trend_boost=round(event_boost + trend_momentum * 0.2, 6),
                    urgency=round(_clamp(0.4 + trend_momentum * 0.6 + max(0.0, event_boost)), 6),
                    recommended_format=blueprint.format,
                    recommended_hook=blueprint.hook_pattern,
                    recommended_duration_minutes=blueprint.target_duration_minutes,
                    estimated_cost_usd=round(float(opp.rationale.get("estimated_cost_usd") or 0.0), 6),
                    action=action,
                    status="ACTIONABLE" if actionable else "WATCH",
                    rationale={
                        "method": "opportunity_intelligence_v1",
                        "note": "Heuristic prioritization based on observed research/trend signals; not a prediction or causal claim.",
                        "event_type": event.event_type if event else None,
                    },
                    evidence={
                        "opportunity": {
                            "score": opp.score,
                            "demand_signal": opp.demand_signal,
                            "competition_signal": opp.competition_signal,
                            "freshness_signal": opp.freshness_signal,
                            "gap_signal": opp.gap_signal,
                            "channel_fit": opp.channel_fit,
                            "occurrence_count": opp.occurrence_count,
                        },
                        "trend": {
                            "event_type": event.event_type if event else None,
                            "delta_signal": event.delta_signal if event else 0.0,
                            "confidence": event.confidence if event else 0.0,
                        },
                        "memory_fit": round(memory_fit, 6),
                    },
                )
                self.db.add(decision)
                if decision.status == "ACTIONABLE":
                    actionable += 1

            run.opportunity_count = len(opportunities)
            run.actionable_count = actionable
            run.status = "SUCCEEDED"
            run.finished_at = datetime.utcnow()
            run.metadata_json = {"min_score": min_score, "trend_window_days": 14}
            await self.db.commit()
            return run
        except Exception as exc:
            run.status = "FAILED"
            run.finished_at = datetime.utcnow()
            run.error_message = str(exc)[:4000]
            await self.db.commit()
            raise

    async def latest_decisions(self, *, channel_id: str, limit: int = 50) -> list[OpportunityDecision]:
        cid = uuid.UUID(channel_id)
        if not await self.db.get(Channel, cid):
            raise ValueError("Channel not found")
        latest_run = await self.db.scalar(
            select(OpportunityAnalysisRun).where(
                OpportunityAnalysisRun.channel_id == cid,
                OpportunityAnalysisRun.status == "SUCCEEDED",
            ).order_by(OpportunityAnalysisRun.created_at.desc()).limit(1)
        )
        if not latest_run:
            return []
        q = await self.db.execute(
            select(OpportunityDecision).where(OpportunityDecision.analysis_run_id == latest_run.id)
            .order_by(OpportunityDecision.priority_score.desc()).limit(max(1, min(limit, 100)))
        )
        return list(q.scalars().all())

    async def list_runs(self, *, channel_id: str, limit: int = 20) -> list[OpportunityAnalysisRun]:
        if not await self.db.get(Channel, uuid.UUID(channel_id)):
            raise ValueError("Channel not found")
        q = await self.db.execute(
            select(OpportunityAnalysisRun).where(OpportunityAnalysisRun.channel_id == uuid.UUID(channel_id))
            .order_by(OpportunityAnalysisRun.created_at.desc()).limit(max(1, min(limit, 100)))
        )
        return list(q.scalars().all())

    async def seed_topics(self, *, channel_id: str, limit: int = 8) -> list[str]:
        rows = await self.latest_decisions(channel_id=channel_id, limit=limit)
        if rows:
            opp_ids = [x.opportunity_id for x in rows if x.action in {"EXPLORE_NOW", "EXPLORE", "REFINE"}]
            if opp_ids:
                q = await self.db.execute(select(ResearchOpportunity).where(ResearchOpportunity.id.in_(opp_ids)))
                by_id = {x.id: x.topic for x in q.scalars().all()}
                return [by_id[x] for x in opp_ids if x in by_id][:limit]
        return []

    def _topic_key(self, topic: str) -> str:
        return "+".join(sorted(_tokens(topic))[:3])

    def _fuzzy_event(self, topic: str, events: list[TrendEvent]) -> TrendEvent | None:
        for event in events:
            if _overlap(topic, event.topic_label) >= 0.25:
                return event
        return None

    def _memory_fit(self, topic: str, memory: dict[str, Any]) -> float:
        clusters = memory.get("topic_clusters") or []
        if not clusters:
            return 0.0
        values = []
        for cluster in clusters:
            label = cluster.get("topic") if isinstance(cluster, dict) else cluster
            if label:
                values.append(_overlap(topic, str(label)))
        return max(values, default=0.0)


def serialize_decision(row: OpportunityDecision, opportunity: ResearchOpportunity | None = None) -> dict:
    return {
        "id": str(row.id),
        "analysis_run_id": str(row.analysis_run_id),
        "channel_id": str(row.channel_id),
        "opportunity_id": str(row.opportunity_id),
        "trend_event_id": str(row.trend_event_id) if row.trend_event_id else None,
        "topic": opportunity.topic if opportunity else None,
        "priority_score": row.priority_score,
        "base_score": row.base_score,
        "trend_boost": row.trend_boost,
        "urgency": row.urgency,
        "recommended_format": row.recommended_format,
        "recommended_hook": row.recommended_hook,
        "recommended_duration_minutes": row.recommended_duration_minutes,
        "estimated_cost_usd": row.estimated_cost_usd,
        "action": row.action,
        "status": row.status,
        "rationale": row.rationale or {},
        "evidence": row.evidence or {},
        "created_at": row.created_at,
    }


def serialize_run(row: OpportunityAnalysisRun) -> dict:
    return {
        "id": str(row.id), "channel_id": str(row.channel_id), "goal": row.goal,
        "status": row.status, "opportunity_count": row.opportunity_count,
        "actionable_count": row.actionable_count, "started_at": row.started_at,
        "finished_at": row.finished_at, "error_message": row.error_message,
        "metadata": row.metadata_json or {},
    }
