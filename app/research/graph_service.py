from __future__ import annotations
import uuid
import hashlib
from datetime import datetime, timedelta
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Channel, ResearchNode, ResearchEdge, ResearchOpportunity
from app.research.factory import get_research_provider
from app.research.opportunity import OpportunityDetector
from app.trends.diff import TrendDiffService


class ResearchGraphService:
    def __init__(self, provider_name: str | None = None, provider_config: dict | None = None):
        self.provider = get_research_provider(provider_name, provider_config)
        self.detector = OpportunityDetector()

    async def scan(
        self,
        db: AsyncSession,
        *,
        channel_id: str,
        query: str,
        max_results: int = 10,
        published_after_days: int | None = 30,
        schedule_id: str | None = None,
        run_id: str | None = None,
    ) -> dict:
        channel = await db.get(Channel, uuid.UUID(channel_id))
        if not channel:
            raise ValueError("Channel not found")
        provider_kwargs = {"query": query, "max_results": max_results}
        if self.provider.name == "youtube_data_api":
            result = await self.provider.search(**provider_kwargs, published_after_days=published_after_days)
        else:
            result = await self.provider.search(**provider_kwargs)
        results = result.get("results") or []
        query_key = f"query:{query.strip().lower()}"
        query_node = await self._upsert_node(db, channel.id, "query", query_key, query.strip(), None, {"provider": self.provider.name})
        source_node_ids: list[str] = []
        created_edges = 0
        for item in results:
            external_id = str(item.get("id") or item.get("url") or item.get("title") or uuid.uuid4())
            node = await self._upsert_node(
                db,
                channel.id,
                "video",
                external_id,
                str(item.get("title") or "Untitled"),
                item.get("url"),
                item,
            )
            source_node_ids.append(str(node.id))
            if item.get("channel_id"):
                channel_node = await self._upsert_node(
                    db, channel.id, "competitor_channel", str(item["channel_id"]),
                    str(item.get("channel_title") or item["channel_id"]),
                    f"https://www.youtube.com/channel/{item['channel_id']}",
                    {"channel_id": item["channel_id"]},
                )
                created_edges += await self._upsert_edge(db, channel.id, query_node.id, node.id, "returned")
                created_edges += await self._upsert_edge(db, channel.id, channel_node.id, node.id, "published")
            else:
                created_edges += await self._upsert_edge(db, channel.id, query_node.id, node.id, "returned")

        signals = self.detector.detect(
            channel={"name": channel.name, "niche": channel.niche, "language": channel.language},
            query=query,
            results=results,
            node_ids=source_node_ids,
        )
        opportunities = []
        for signal in signals:
            fingerprint = opportunity_fingerprint(query, signal.topic)
            existing = await db.scalar(
                select(ResearchOpportunity)
                .where(
                    ResearchOpportunity.channel_id == channel.id,
                    ResearchOpportunity.fingerprint == fingerprint,
                )
                .order_by(ResearchOpportunity.updated_at.desc())
                .limit(1)
            )
            if existing:
                existing.query = query
                existing.topic = signal.topic
                existing.score = signal.score
                existing.demand_signal = signal.demand_signal
                existing.competition_signal = signal.competition_signal
                existing.freshness_signal = signal.freshness_signal
                existing.gap_signal = signal.gap_signal
                existing.channel_fit = signal.channel_fit
                existing.rationale = signal.rationale
                existing.source_node_ids = signal.source_node_ids
                existing.last_seen_at = datetime.utcnow()
                existing.occurrence_count = int(existing.occurrence_count or 0) + 1
                existing.status = "DISCOVERED"
                row = existing
            else:
                row = ResearchOpportunity(
                    channel_id=channel.id,
                    query=query,
                    topic=signal.topic,
                    fingerprint=fingerprint,
                    score=signal.score,
                    demand_signal=signal.demand_signal,
                    competition_signal=signal.competition_signal,
                    freshness_signal=signal.freshness_signal,
                    gap_signal=signal.gap_signal,
                    channel_fit=signal.channel_fit,
                    rationale=signal.rationale,
                    source_node_ids=signal.source_node_ids,
                    last_seen_at=datetime.utcnow(),
                    occurrence_count=1,
                )
                db.add(row)
            opportunities.append(row)
        trend = await TrendDiffService(db).record_snapshot(
            channel_id=channel_id,
            query=query,
            provider=self.provider.name,
            results=results,
            metadata=result.get("metadata") or {},
            schedule_id=schedule_id,
            run_id=run_id,
        )
        await db.commit()
        for row in opportunities:
            await db.refresh(row)
        return {
            "channel_id": channel_id,
            "query": query,
            "provider": self.provider.name,
            "result_count": len(results),
            "graph": {"query_node_id": str(query_node.id), "source_node_ids": source_node_ids, "edges_created": created_edges},
            "opportunities": [serialize_opportunity(row) for row in opportunities],
            "metadata": {**(result.get("metadata") or {}), "trend": trend},
        }

    async def _upsert_node(self, db: AsyncSession, channel_id, node_type: str, external_id: str, label: str, url: str | None, data: dict) -> ResearchNode:
        q = await db.execute(select(ResearchNode).where(
            ResearchNode.channel_id == channel_id,
            ResearchNode.node_type == node_type,
            ResearchNode.external_id == external_id,
        ))
        node = q.scalar_one_or_none()
        if node:
            node.label = label or node.label
            node.url = url or node.url
            node.data = data or node.data
            return node
        node = ResearchNode(channel_id=channel_id, node_type=node_type, external_id=external_id, label=label, url=url, data=data, confidence=0.6)
        db.add(node)
        await db.flush()
        return node

    async def _upsert_edge(self, db: AsyncSession, channel_id, source_id, target_id, relation: str) -> int:
        q = await db.execute(select(ResearchEdge).where(
            ResearchEdge.channel_id == channel_id,
            ResearchEdge.source_node_id == source_id,
            ResearchEdge.target_node_id == target_id,
            ResearchEdge.relation == relation,
        ))
        if q.scalar_one_or_none():
            return 0
        db.add(ResearchEdge(channel_id=channel_id, source_node_id=source_id, target_node_id=target_id, relation=relation, weight=1.0))
        return 1


async def list_opportunities(db: AsyncSession, channel_id: str, limit: int = 50) -> list[ResearchOpportunity]:
    q = await db.execute(
        select(ResearchOpportunity)
        .where(ResearchOpportunity.channel_id == uuid.UUID(channel_id))
        .order_by(ResearchOpportunity.score.desc(), ResearchOpportunity.created_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    return list(q.scalars().all())


async def graph_snapshot(db: AsyncSession, channel_id: str, limit: int = 150) -> dict:
    q_nodes = await db.execute(
        select(ResearchNode)
        .where(ResearchNode.channel_id == uuid.UUID(channel_id))
        .order_by(ResearchNode.created_at.desc())
        .limit(min(max(limit, 1), 300))
    )
    nodes = list(q_nodes.scalars().all())
    ids = {row.id for row in nodes}
    if not ids:
        return {"channel_id": channel_id, "nodes": [], "edges": []}
    q_edges = await db.execute(select(ResearchEdge).where(
        ResearchEdge.channel_id == uuid.UUID(channel_id),
        ResearchEdge.source_node_id.in_(ids),
        ResearchEdge.target_node_id.in_(ids),
    ).limit(600))
    edges = list(q_edges.scalars().all())
    return {
        "channel_id": channel_id,
        "nodes": [{"id": str(x.id), "node_type": x.node_type, "external_id": x.external_id, "label": x.label, "url": x.url, "data": x.data or {}, "confidence": x.confidence} for x in nodes],
        "edges": [{"id": str(x.id), "source": str(x.source_node_id), "target": str(x.target_node_id), "relation": x.relation, "weight": x.weight} for x in edges],
    }


def serialize_opportunity(row: ResearchOpportunity) -> dict:
    return {
        "id": str(row.id), "channel_id": str(row.channel_id), "query": row.query, "topic": row.topic,
        "score": row.score, "demand_signal": row.demand_signal, "competition_signal": row.competition_signal,
        "fingerprint": row.fingerprint, "last_seen_at": row.last_seen_at, "occurrence_count": row.occurrence_count,
        "freshness_signal": row.freshness_signal, "gap_signal": row.gap_signal, "channel_fit": row.channel_fit,
        "rationale": row.rationale or {}, "source_node_ids": row.source_node_ids or [], "status": row.status,
        "created_at": row.created_at,
    }


def opportunity_fingerprint(query: str, topic: str) -> str:
    payload = f"{query.strip().lower()}::{topic.strip().lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
