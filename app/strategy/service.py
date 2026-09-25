from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalyticsSnapshot, Channel, ChannelMemory, ResearchOpportunity, TrendEvent


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _tokens(value: str) -> set[str]:
    return {x for x in value.lower().replace("/", " ").replace("-", " ").split() if len(x) >= 4}


class PortfolioStrategyBrain:
    """Connects Global Radar signals to channel twins, audience signals and growth hypotheses.

    This layer is deliberately evidence-first: it consumes persisted research, trend and
    analytics observations and produces auditable hypotheses. It does not claim causality.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def build(self, *, owner_key: str, organization_id=None, horizon_videos: int = 20) -> dict[str, Any]:
        horizon_videos = max(10, min(int(horizon_videos), 30))
        channel_filter = (Channel.organization_id == organization_id) if organization_id else ((Channel.organization_id.is_(None)) & (Channel.owner_id == owner_key))
        channels = list((await self.db.execute(select(Channel).where(channel_filter).order_by(Channel.created_at.asc()))).scalars().all())
        result = {"generated_at": datetime.utcnow().isoformat(), "version": "strategy_brain_v1", "channels": [], "portfolio_structure": [], "video_slate": []}
        for channel in channels:
            result["channels"].append(await self._channel_twin(channel, horizon_videos))
        result["portfolio_structure"] = self._portfolio_structure(result["channels"])
        result["video_slate"] = self._video_slate(result["channels"], horizon_videos)
        return result

    async def _channel_twin(self, channel: Channel, horizon: int) -> dict[str, Any]:
        memory = await self.db.scalar(select(ChannelMemory).where(ChannelMemory.channel_id == channel.id))
        since = datetime.utcnow() - timedelta(days=28)
        metrics = await self.db.execute(select(
            func.coalesce(func.sum(AnalyticsSnapshot.views), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.watch_time_minutes), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.subscribers_gained), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.impressions), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.likes), 0),
            func.coalesce(func.sum(AnalyticsSnapshot.comments), 0),
        ).where(AnalyticsSnapshot.channel_id == channel.id, AnalyticsSnapshot.collected_at >= since))
        views, watch, gained, impressions, likes, comments = metrics.one()
        opportunities = list((await self.db.execute(select(ResearchOpportunity).where(ResearchOpportunity.channel_id == channel.id).order_by(ResearchOpportunity.score.desc(), ResearchOpportunity.last_seen_at.desc()).limit(30))).scalars().all())
        trends = list((await self.db.execute(select(TrendEvent).where(TrendEvent.channel_id == channel.id, TrendEvent.created_at >= datetime.utcnow() - timedelta(days=14)).order_by(TrendEvent.created_at.desc()).limit(30))).scalars().all())
        ctr = _clamp((float(likes or 0) + float(comments or 0)) / max(float(views or 1), 1) * 8.0)
        engagement = _clamp((float(likes or 0) + 3 * float(comments or 0)) / max(float(views or 1), 1) * 12.0)
        audience = {
            "watch_intent": _clamp(float(watch or 0) / max(float(views or 1), 1) * 4.0),
            "engagement_signal": round(engagement, 6),
            "discovery_signal": _clamp(float(impressions or 0) / max(float(views or 1), 1) / 20.0),
            "subscriber_conversion": _clamp(float(gained or 0) / max(float(views or 1), 1) * 20.0),
            "topic_clusters": list((memory.topic_clusters if memory else []) or [])[:12],
            "hook_patterns": list((memory.hook_patterns if memory else []) or [])[:8],
        }
        hypotheses = []
        for opp in opportunities[:8]:
            matching = next((t for t in trends if _tokens(opp.topic) & _tokens(t.topic_label)), None)
            evidence = {"opportunity_score": float(opp.score or 0), "demand": float(opp.demand_signal or 0), "gap": float(opp.gap_signal or 0), "competition": float(opp.competition_signal or 0), "trend_event": matching.event_type if matching else None, "trend_delta": float(matching.delta_signal or 0) if matching else 0.0}
            strength = _clamp(float(opp.score or 0) * 0.55 + float(opp.channel_fit or 0) * 0.2 + float(opp.gap_signal or 0) * 0.15 + (0.1 if matching and matching.event_type in {"NEW", "RISING"} else 0))
            hypotheses.append({"topic": opp.topic, "hypothesis": f"Audience interest may be exploitable through a focused {opp.topic} angle.", "strength": round(strength, 6), "evidence": evidence})
        return {
            "channel": {"id": str(channel.id), "name": channel.name, "niche": channel.niche, "language": channel.language, "youtube_channel_id": channel.youtube_channel_id},
            "digital_twin": {"objective": "learn_and_grow", "recent_28d": {"views": int(views or 0), "watch_time_minutes": float(watch or 0), "subscribers_gained": int(gained or 0), "impressions": int(impressions or 0)}, "signals": {"engagement": round(engagement, 6), "discovery": round(ctr, 6)}},
            "audience_graph": audience,
            "growth_hypotheses": hypotheses,
            "radar_topics": [o.topic for o in opportunities[:12]],
            "recommended_video_count": min(horizon, max(10, len(opportunities) * 2)),
        }

    @staticmethod
    def _portfolio_structure(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(channels, key=lambda c: (c["digital_twin"]["recent_28d"]["views"], c["digital_twin"]["recent_28d"]["watch_time_minutes"]), reverse=True)
        roles = ["core_growth", "experimental_growth", "authority", "emerging"]
        return [{"channel_id": c["channel"]["id"], "channel_name": c["channel"]["name"], "role": roles[i] if i < len(roles) else "emerging", "reason": "Derived from observed channel signals and available opportunity coverage."} for i, c in enumerate(ordered)]

    @staticmethod
    def _video_slate(channels: list[dict[str, Any]], horizon: int) -> list[dict[str, Any]]:
        candidates = []
        for c in channels:
            for h in c["growth_hypotheses"]:
                candidates.append({"channel_id": c["channel"]["id"], "channel_name": c["channel"]["name"], "topic": h["topic"], "hypothesis_strength": h["strength"], "evidence": h["evidence"], "status": "PROPOSED"})
        candidates.sort(key=lambda x: x["hypothesis_strength"], reverse=True)
        return candidates[:horizon]
