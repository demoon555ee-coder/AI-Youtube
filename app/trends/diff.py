from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ResearchSnapshot, TrendEvent

STOPWORDS = {
    "about", "after", "again", "against", "because", "before", "being", "between",
    "could", "first", "from", "have", "into", "just", "more", "most", "other",
    "over", "same", "some", "than", "that", "their", "there", "these", "they",
    "this", "those", "through", "under", "very", "what", "when", "where", "which",
    "while", "with", "would", "your", "will", "using", "used", "how", "why", "guide",
    "review", "official", "video", "episode", "explained", "shorts",
    "are", "is", "and", "the", "for", "you", "can", "changing", "change", "build",
}


def topic_key_from_title(title: str) -> str:
    tokens = [
        token.lower()
        for token in re.findall(r"[a-zA-Z0-9а-яА-Я][a-zA-Z0-9а-яА-Я_-]{2,}", title)
        if token.lower() not in STOPWORDS
    ]
    if not tokens:
        return "untitled"
    counts = Counter(tokens)
    selected = sorted(counts, key=lambda x: (-counts[x], x))[:3]
    return "+".join(selected)


def topic_signal(item: dict[str, Any]) -> float:
    views = float(item.get("views") or 0)
    likes = float(item.get("likes") or 0)
    comments = float(item.get("comments") or 0)
    engagement = min(1.0, (likes + comments * 2.0) / max(1.0, views) * 100.0)
    view_signal = min(1.0, __import__("math").log1p(max(0.0, views)) / __import__("math").log1p(1e9))
    return round(view_signal * 0.8 + engagement * 0.2, 6)


def build_topic_signals(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for item in results:
        key = topic_key_from_title(str(item.get("title") or ""))
        row = groups.setdefault(key, {"topic_key": key, "topic_label": str(item.get("title") or key), "signals": [], "video_ids": []})
        row["signals"].append(topic_signal(item))
        if item.get("id"):
            row["video_ids"].append(str(item["id"]))
    output = []
    for row in groups.values():
        values = row["signals"]
        output.append({
            "topic_key": row["topic_key"],
            "topic_label": row["topic_label"],
            "signal": round(sum(values) / max(1, len(values)), 6),
            "result_count": len(values),
            "video_ids": row["video_ids"][:20],
        })
    return sorted(output, key=lambda x: x["signal"], reverse=True)


class TrendDiffService:
    """Compares consecutive research snapshots. 'DISAPPEARING' means absent from the current observed sample, not confirmed market disappearance."""

    def __init__(self, db: AsyncSession, *, rising_threshold: float = 0.08, fading_threshold: float = 0.08):
        self.db = db
        self.rising_threshold = rising_threshold
        self.fading_threshold = fading_threshold

    async def record_snapshot(
        self,
        *,
        channel_id: str,
        query: str,
        provider: str,
        results: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        schedule_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        channel_uuid = uuid.UUID(channel_id)
        previous = await self.db.scalar(
            select(ResearchSnapshot)
            .where(ResearchSnapshot.channel_id == channel_uuid, ResearchSnapshot.query == query)
            .order_by(ResearchSnapshot.captured_at.desc())
            .limit(1)
        )
        topics = build_topic_signals(results)
        snapshot = ResearchSnapshot(
            channel_id=channel_uuid,
            schedule_id=uuid.UUID(schedule_id) if schedule_id else None,
            run_id=uuid.UUID(run_id) if run_id else None,
            query=query,
            provider=provider,
            captured_at=datetime.utcnow(),
            result_count=len(results),
            avg_views=round(sum(float(x.get("views") or 0) for x in results) / max(1, len(results)), 2),
            max_views=max((float(x.get("views") or 0) for x in results), default=0.0),
            unique_channels=len({str(x.get("channel_id")) for x in results if x.get("channel_id")}),
            topics_json=topics,
            metadata_json=metadata or {},
        )
        self.db.add(snapshot)
        await self.db.flush()

        previous_topics = {x.get("topic_key"): x for x in (previous.topics_json or [])} if previous else {}
        current_topics = {x.get("topic_key"): x for x in topics}
        events: list[TrendEvent] = []

        for key, current in current_topics.items():
            prev = previous_topics.get(key)
            if not prev:
                event_type = "NEW"
                previous_signal = 0.0
                delta = current["signal"]
                confidence = min(1.0, 0.45 + current["result_count"] * 0.08)
            else:
                previous_signal = float(prev.get("signal") or 0.0)
                delta = current["signal"] - previous_signal
                if delta >= self.rising_threshold:
                    event_type = "RISING"
                elif delta <= -self.fading_threshold:
                    event_type = "FALLING"
                else:
                    event_type = "STABLE"
                confidence = min(1.0, 0.5 + min(0.5, abs(delta) * 2.0))
            if event_type == "STABLE":
                continue
            event = TrendEvent(
                channel_id=channel_uuid,
                snapshot_id=snapshot.id,
                query=query,
                topic_key=key,
                topic_label=str(current.get("topic_label") or key),
                event_type=event_type,
                current_signal=float(current.get("signal") or 0.0),
                previous_signal=previous_signal,
                delta_signal=delta,
                confidence=confidence,
                rationale={
                    "comparison": "consecutive_research_snapshots",
                    "previous_snapshot_id": str(previous.id) if previous else None,
                    "current_result_count": len(results),
                    "previous_result_count": int(previous.result_count) if previous else 0,
                    "note": "FALLING indicates a declining signal; absent topics are only treated as sample disappearance after explicit lookback logic.",
                },
            )
            self.db.add(event)
            events.append(event)

        if previous:
            # Topics seen in the previous sample but absent from the current sample are marked as DISAPPEARING.
            # This is explicitly a sample-level observation, not proof that the topic disappeared from YouTube overall.
            for key, prev in previous_topics.items():
                if key in current_topics:
                    continue
                event = TrendEvent(
                    channel_id=channel_uuid,
                    snapshot_id=snapshot.id,
                    query=query,
                    topic_key=key,
                    topic_label=str(prev.get("topic_label") or key),
                    event_type="DISAPPEARING",
                    current_signal=0.0,
                    previous_signal=float(prev.get("signal") or 0.0),
                    delta_signal=-float(prev.get("signal") or 0.0),
                    confidence=min(1.0, 0.45 + float(prev.get("result_count") or 0) * 0.08),
                    rationale={
                        "comparison": "sample_membership",
                        "previous_snapshot_id": str(previous.id),
                        "note": "Absent from the current observed sample; not proof of broader disappearance.",
                    },
                )
                self.db.add(event)
                events.append(event)

        await self.db.flush()
        return {
            "snapshot_id": str(snapshot.id),
            "previous_snapshot_id": str(previous.id) if previous else None,
            "topic_count": len(topics),
            "events": [serialize_trend_event(x) for x in events],
        }

    async def list_events(self, channel_id: str, *, query: str | None = None, event_type: str | None = None, limit: int = 50) -> list[TrendEvent]:
        query_stmt = select(TrendEvent).where(TrendEvent.channel_id == uuid.UUID(channel_id))
        if query:
            query_stmt = query_stmt.where(TrendEvent.query == query)
        if event_type:
            query_stmt = query_stmt.where(TrendEvent.event_type == event_type)
        result = await self.db.execute(query_stmt.order_by(TrendEvent.created_at.desc()).limit(min(max(1, limit), 200)))
        return list(result.scalars().all())

    async def list_snapshots(self, channel_id: str, *, query: str | None = None, limit: int = 30) -> list[ResearchSnapshot]:
        query_stmt = select(ResearchSnapshot).where(ResearchSnapshot.channel_id == uuid.UUID(channel_id))
        if query:
            query_stmt = query_stmt.where(ResearchSnapshot.query == query)
        result = await self.db.execute(query_stmt.order_by(ResearchSnapshot.captured_at.desc()).limit(min(max(1, limit), 100)))
        return list(result.scalars().all())


def serialize_trend_event(row: TrendEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "channel_id": str(row.channel_id),
        "snapshot_id": str(row.snapshot_id),
        "query": row.query,
        "topic_key": row.topic_key,
        "topic_label": row.topic_label,
        "event_type": row.event_type,
        "current_signal": row.current_signal,
        "previous_signal": row.previous_signal,
        "delta_signal": row.delta_signal,
        "confidence": row.confidence,
        "rationale": row.rationale or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def serialize_snapshot(row: ResearchSnapshot) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "channel_id": str(row.channel_id),
        "schedule_id": str(row.schedule_id) if row.schedule_id else None,
        "run_id": str(row.run_id) if row.run_id else None,
        "query": row.query,
        "provider": row.provider,
        "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        "result_count": row.result_count,
        "avg_views": row.avg_views,
        "max_views": row.max_views,
        "unique_channels": row.unique_channels,
        "topics": row.topics_json or [],
        "metadata": row.metadata_json or {},
    }
