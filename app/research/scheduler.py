from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.researched import generate_from_opportunities
from app.models import Channel, ResearchRun, ResearchSchedule
from app.research.graph_service import ResearchGraphService
from app.opportunity_intelligence.service import OpportunityIntelligenceService


VALID_GOALS = {"growth", "authority", "monetization", "balanced"}


class ResearchSchedulerService:
    """Durable, database-backed scheduler for autonomous research scans."""

    def __init__(self, db: AsyncSession, *, lease_minutes: int = 20):
        self.db = db
        self.lease = timedelta(minutes=max(1, lease_minutes))

    async def create_schedule(
        self,
        *,
        channel_id: str,
        name: str,
        query: str,
        cadence_hours: float = 24,
        next_run_at: datetime | None = None,
        provider: str | None = None,
        max_results: int = 10,
        published_after_days: int | None = 30,
        auto_generate_ideas: bool = False,
        idea_count: int = 5,
        goal: str = "balanced",
        catch_up: bool = False,
        max_runs_per_day: int = 3,
    ) -> ResearchSchedule:
        channel = await self.db.get(Channel, uuid.UUID(channel_id))
        if not channel:
            raise ValueError("Channel not found")
        if not name.strip():
            raise ValueError("Schedule name is required")
        if not query.strip():
            raise ValueError("Research query is required")
        if not (1 <= cadence_hours <= 168):
            raise ValueError("cadence_hours must be between 1 and 168")
        if goal not in VALID_GOALS:
            raise ValueError(f"Unsupported goal: {goal}")
        if not (3 <= max_results <= 50):
            raise ValueError("max_results must be between 3 and 50")
        if not (1 <= idea_count <= 50):
            raise ValueError("idea_count must be between 1 and 50")
        if not (1 <= max_runs_per_day <= 24):
            raise ValueError("max_runs_per_day must be between 1 and 24")

        existing = await self.db.scalar(
            select(ResearchSchedule).where(
                ResearchSchedule.channel_id == channel.id,
                ResearchSchedule.name == name.strip(),
            )
        )
        if existing:
            raise ValueError("A schedule with this name already exists for the channel")

        now = datetime.utcnow()
        schedule = ResearchSchedule(
            channel_id=channel.id,
            name=name.strip(),
            query=query.strip(),
            provider=provider,
            cadence_hours=float(cadence_hours),
            next_run_at=normalize_utc_naive(next_run_at) if next_run_at else now,
            enabled=True,
            max_results=max_results,
            published_after_days=published_after_days,
            auto_generate_ideas=auto_generate_ideas,
            idea_count=idea_count,
            goal=goal,
            catch_up=catch_up,
            max_runs_per_day=max_runs_per_day,
            metadata_json={"created_by": "api"},
        )
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def claim_due(self, *, limit: int = 3) -> list[uuid.UUID]:
        now = datetime.utcnow()
        q = await self.db.execute(
            select(ResearchSchedule)
            .where(
                ResearchSchedule.enabled.is_(True),
                ResearchSchedule.next_run_at <= now,
                (ResearchSchedule.locked_until.is_(None) | (ResearchSchedule.locked_until < now)),
            )
            .order_by(ResearchSchedule.next_run_at.asc())
            .limit(min(max(limit, 1), 20))
            .with_for_update(skip_locked=True)
        )
        schedules = list(q.scalars().all())
        claimed: list[uuid.UUID] = []
        for schedule in schedules:
            manual_requested = bool((schedule.metadata_json or {}).get("manual_run_requested"))
            todays_runs = await self._runs_today(schedule.id, now)
            if not manual_requested and todays_runs >= schedule.max_runs_per_day:
                schedule.next_run_at = self._next_utc_day(now)
                schedule.last_status = "DAILY_LIMIT"
                continue
            metadata = dict(schedule.metadata_json or {})
            metadata["requested_trigger_type"] = "manual" if manual_requested else "scheduled"
            metadata["manual_run_requested"] = False
            schedule.metadata_json = metadata
            schedule.locked_until = now + self.lease
            schedule.last_status = "CLAIMED"
            claimed.append(schedule.id)
        await self.db.commit()
        return claimed

    async def process_due(self, *, limit: int = 3) -> list[dict]:
        claimed_ids = await self.claim_due(limit=limit)
        results: list[dict] = []
        for schedule_id in claimed_ids:
            results.append(await self.run_schedule(schedule_id))
        return results

    async def run_now(self, schedule_id: str) -> ResearchSchedule:
        schedule = await self.db.get(ResearchSchedule, uuid.UUID(schedule_id))
        if not schedule:
            raise ValueError("Research schedule not found")
        now = datetime.utcnow()
        if not schedule.enabled:
            raise ValueError("Research schedule is disabled")
        if schedule.locked_until and schedule.locked_until > now:
            raise ValueError("Research schedule is already running")
        metadata = dict(schedule.metadata_json or {})
        metadata["manual_run_requested"] = True
        schedule.metadata_json = metadata
        schedule.next_run_at = now
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def run_schedule(self, schedule_id: uuid.UUID | str, *, trigger_type: str = "scheduled") -> dict:
        schedule = await self.db.get(ResearchSchedule, uuid.UUID(str(schedule_id)))
        if not schedule:
            raise ValueError("Research schedule not found")
        if not schedule.enabled and trigger_type == "scheduled":
            return {"schedule_id": str(schedule.id), "status": "DISABLED"}

        requested_trigger_type = str((schedule.metadata_json or {}).get("requested_trigger_type") or trigger_type)
        run = ResearchRun(
            schedule_id=schedule.id,
            channel_id=schedule.channel_id,
            query=schedule.query,
            provider=schedule.provider or "default",
            trigger_type=requested_trigger_type,
            status="RUNNING",
            metadata_json={"cadence_hours": schedule.cadence_hours},
        )
        self.db.add(run)
        schedule.last_run_at = datetime.utcnow()
        schedule.last_status = "RUNNING"
        schedule.last_error = None
        await self.db.commit()
        await self.db.refresh(run)

        try:
            result = await ResearchGraphService(provider_name=schedule.provider).scan(
                self.db,
                channel_id=str(schedule.channel_id),
                query=schedule.query,
                max_results=schedule.max_results,
                published_after_days=schedule.published_after_days,
                schedule_id=str(schedule.id),
                run_id=str(run.id),
            )
            opportunities = result.get("opportunities") or []
            idea_count = 0
            intelligence_run = await OpportunityIntelligenceService(self.db).analyze(
                channel_id=str(schedule.channel_id), goal=schedule.goal, limit=min(50, max(10, len(opportunities)))
            )
            intelligent_decisions = await OpportunityIntelligenceService(self.db).latest_decisions(
                channel_id=str(schedule.channel_id), limit=min(10, schedule.idea_count)
            )
            if schedule.auto_generate_ideas and opportunities:
                intelligent_ids = [row.opportunity_id for row in intelligent_decisions if row.action in {"EXPLORE_NOW", "EXPLORE", "REFINE"}]
                opportunity_ids = [str(x) for x in intelligent_ids] or [x["id"] for x in opportunities[: min(10, len(opportunities))] if x.get("id")]
                if opportunity_ids:
                    ideas = await generate_from_opportunities(
                        self.db,
                        channel_id=str(schedule.channel_id),
                        opportunity_ids=opportunity_ids,
                        count=schedule.idea_count,
                        goal=schedule.goal,
                    )
                    idea_count = len(ideas)

            now = datetime.utcnow()
            run.status = "SUCCEEDED"
            run.finished_at = now
            run.result_count = int(result.get("result_count") or 0)
            run.opportunity_count = len(opportunities)
            run.generated_idea_count = idea_count
            run.provider = str(result.get("provider") or schedule.provider or "default")
            run.metadata_json = {**(run.metadata_json or {}), "research_metadata": result.get("metadata") or {}, "opportunity_intelligence_run_id": str(intelligence_run.id), "opportunity_intelligence_actionable_count": intelligence_run.actionable_count}

            schedule.failure_count = 0
            schedule.last_status = "SUCCEEDED"
            schedule.locked_until = None
            schedule.next_run_at = advance_next_run_at(
                schedule.next_run_at, now, schedule.cadence_hours, schedule.catch_up
            )
            await self.db.commit()
            return {
                "schedule_id": str(schedule.id),
                "run_id": str(run.id),
                "status": run.status,
                "result_count": run.result_count,
                "opportunity_count": run.opportunity_count,
                "generated_idea_count": run.generated_idea_count,
                "next_run_at": schedule.next_run_at.isoformat(),
            }
        except Exception as exc:
            now = datetime.utcnow()
            schedule.failure_count += 1
            backoff = backoff_hours(schedule.failure_count, schedule.cadence_hours)
            schedule.next_run_at = now + timedelta(hours=backoff)
            schedule.last_status = "FAILED"
            schedule.last_error = str(exc)[:4000]
            schedule.locked_until = None
            run.status = "FAILED"
            run.finished_at = now
            run.error_message = str(exc)[:4000]
            run.metadata_json = {**(run.metadata_json or {}), "backoff_hours": backoff}
            await self.db.commit()
            return {
                "schedule_id": str(schedule.id),
                "run_id": str(run.id),
                "status": "FAILED",
                "error": str(exc),
                "next_run_at": schedule.next_run_at.isoformat(),
            }

    async def enable(self, schedule_id: str) -> ResearchSchedule:
        schedule = await self._get(schedule_id)
        schedule.enabled = True
        schedule.locked_until = None
        if schedule.next_run_at < datetime.utcnow():
            schedule.next_run_at = datetime.utcnow()
        schedule.last_status = "ENABLED"
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def disable(self, schedule_id: str) -> ResearchSchedule:
        schedule = await self._get(schedule_id)
        schedule.enabled = False
        schedule.locked_until = None
        schedule.last_status = "DISABLED"
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def list_schedules(self, channel_id: str, limit: int = 50) -> list[ResearchSchedule]:
        await self._ensure_channel(channel_id)
        q = await self.db.execute(
            select(ResearchSchedule)
            .where(ResearchSchedule.channel_id == uuid.UUID(channel_id))
            .order_by(ResearchSchedule.enabled.desc(), ResearchSchedule.next_run_at.asc())
            .limit(min(max(limit, 1), 100))
        )
        return list(q.scalars().all())

    async def list_runs(self, schedule_id: str, limit: int = 50) -> list[ResearchRun]:
        await self._get(schedule_id)
        q = await self.db.execute(
            select(ResearchRun)
            .where(ResearchRun.schedule_id == uuid.UUID(schedule_id))
            .order_by(ResearchRun.started_at.desc())
            .limit(min(max(limit, 1), 100))
        )
        return list(q.scalars().all())

    async def _get(self, schedule_id: str) -> ResearchSchedule:
        schedule = await self.db.get(ResearchSchedule, uuid.UUID(schedule_id))
        if not schedule:
            raise ValueError("Research schedule not found")
        return schedule

    async def _ensure_channel(self, channel_id: str) -> Channel:
        channel = await self.db.get(Channel, uuid.UUID(channel_id))
        if not channel:
            raise ValueError("Channel not found")
        return channel

    async def _runs_today(self, schedule_id: uuid.UUID, now: datetime) -> int:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(await self.db.scalar(
            select(func.count(ResearchRun.id)).where(
                ResearchRun.schedule_id == schedule_id,
                ResearchRun.started_at >= start,
            )
        ) or 0)

    @staticmethod
    def _next_utc_day(now: datetime) -> datetime:
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def normalize_utc_naive(value: datetime) -> datetime:
    """Store API timestamps consistently as UTC-naive values for TIMESTAMP columns."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def backoff_hours(failure_count: int, cadence_hours: float) -> float:
    """Bounded exponential backoff that never exceeds the schedule cadence."""
    return min(float(cadence_hours), max(1.0, float(2 ** min(max(failure_count, 1), 6))))


def advance_next_run_at(previous: datetime, now: datetime, cadence_hours: float, catch_up: bool) -> datetime:
    """Advance a periodic schedule without creating unbounded catch-up storms."""
    cadence = timedelta(hours=float(cadence_hours))
    if not catch_up:
        return now + cadence
    candidate = previous + cadence
    steps = 0
    while candidate <= now and steps < 1000:
        candidate += cadence
        steps += 1
    return candidate


def serialize_schedule(schedule: ResearchSchedule) -> dict:
    return {
        "id": str(schedule.id),
        "channel_id": str(schedule.channel_id),
        "name": schedule.name,
        "query": schedule.query,
        "provider": schedule.provider,
        "cadence_hours": schedule.cadence_hours if schedule.cadence_hours is not None else 24.0,
        "next_run_at": schedule.next_run_at,
        "enabled": schedule.enabled if schedule.enabled is not None else True,
        "max_results": schedule.max_results if schedule.max_results is not None else 10,
        "published_after_days": schedule.published_after_days,
        "auto_generate_ideas": schedule.auto_generate_ideas if schedule.auto_generate_ideas is not None else False,
        "idea_count": schedule.idea_count if schedule.idea_count is not None else 5,
        "goal": schedule.goal or "balanced",
        "catch_up": schedule.catch_up if schedule.catch_up is not None else False,
        "max_runs_per_day": schedule.max_runs_per_day if schedule.max_runs_per_day is not None else 3,
        "last_run_at": schedule.last_run_at,
        "last_status": schedule.last_status or "NEVER_RUN",
        "failure_count": schedule.failure_count if schedule.failure_count is not None else 0,
        "last_error": schedule.last_error,
        "locked_until": schedule.locked_until,
    }


def serialize_run(run: ResearchRun) -> dict:
    return {
        "id": str(run.id),
        "schedule_id": str(run.schedule_id),
        "channel_id": str(run.channel_id),
        "query": run.query,
        "provider": run.provider or "mock",
        "trigger_type": run.trigger_type or "scheduled",
        "status": run.status or "RUNNING",
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "result_count": run.result_count if run.result_count is not None else 0,
        "opportunity_count": run.opportunity_count if run.opportunity_count is not None else 0,
        "generated_idea_count": run.generated_idea_count if run.generated_idea_count is not None else 0,
        "error_message": run.error_message,
        "metadata": run.metadata_json or {},
    }
