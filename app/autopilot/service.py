from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.strategy import ContentStrategyEngine
from app.content.service import load_channel_memory
from app.models.channel import Channel
from app.models.content import ContentIdea
from app.models.autopilot import ContentPlan, ContentPlanItem
from app.models.domain import VideoProject
from app.content.intelligence import ContentIntelligenceEngine
from app.models.intelligence import ContentBlueprint
from app.opportunity_intelligence.service import OpportunityIntelligenceService

GOALS = {"growth", "authority", "monetization", "balanced"}


@dataclass
class ScheduleSlot:
    local_date: date
    local_datetime: datetime
    utc_datetime: datetime


def parse_hhmm(value: str) -> time:
    try:
        hour, minute = value.split(":", 1)
        return time(int(hour), int(minute))
    except (ValueError, AttributeError) as exc:
        raise ValueError("publish_time must use HH:MM") from exc


def build_schedule_slots(*, start_date: date, horizon_days: int, timezone_name: str, publish_time: str, cadence_per_week: int, weekdays: list[int] | None = None) -> list[ScheduleSlot]:
    if horizon_days < 1 or horizon_days > 365:
        raise ValueError("horizon_days must be between 1 and 365")
    if cadence_per_week < 1 or cadence_per_week > 7:
        raise ValueError("cadence_per_week must be between 1 and 7")
    tz = ZoneInfo(timezone_name)
    local_time = parse_hhmm(publish_time)
    chosen = sorted(set(weekdays or []))
    if chosen and any(day < 0 or day > 6 for day in chosen):
        raise ValueError("weekdays must contain values from 0 (Monday) to 6 (Sunday)")
    if chosen and len(chosen) != cadence_per_week:
        raise ValueError("when weekdays are provided, their count must equal cadence_per_week")

    slots: list[ScheduleSlot] = []
    end_date = start_date + timedelta(days=horizon_days - 1)
    if not chosen:
        # Spread cadence across a 7-day week deterministically.
        step = 7 / cadence_per_week
        chosen = sorted({int(round(i * step)) % 7 for i in range(cadence_per_week)})
        # Rounding can collide for high cadence; fill missing weekdays.
        day = 0
        while len(chosen) < cadence_per_week:
            if day not in chosen:
                chosen.append(day)
            day += 1
        chosen.sort()

    current = start_date
    while current <= end_date:
        if current.weekday() in chosen:
            local_dt = datetime.combine(current, local_time).replace(tzinfo=tz)
            utc_dt = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
            slots.append(ScheduleSlot(current, local_dt, utc_dt))
        current += timedelta(days=1)
    return slots


class AutopilotService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.strategy = ContentStrategyEngine()
        self.intelligence = ContentIntelligenceEngine()

    async def generate_plan(
        self,
        *,
        channel_id: str,
        name: str,
        start_date: date,
        horizon_days: int,
        cadence_per_week: int,
        publish_time: str,
        weekdays: list[int] | None,
        goal: str,
        timezone_name: str | None,
        production_lead_hours: int,
        auto_publish: bool,
        seed_topics: list[str],
    ) -> ContentPlan:
        channel = await self.db.get(Channel, uuid.UUID(channel_id))
        if not channel:
            raise ValueError("Channel not found")
        goal = goal if goal in GOALS else "balanced"
        tz_name = timezone_name or channel.timezone or "UTC"
        ZoneInfo(tz_name)  # validate timezone
        slots = build_schedule_slots(
            start_date=start_date,
            horizon_days=horizon_days,
            timezone_name=tz_name,
            publish_time=publish_time,
            cadence_per_week=cadence_per_week,
            weekdays=weekdays,
        )
        if not slots:
            raise ValueError("No publication slots were created for the selected weekdays and horizon")

        memory = await load_channel_memory(self.db, channel_id)
        channel_ctx = {"name": channel.name, "niche": channel.niche, "language": channel.language}
        intelligence_topics = []
        if not seed_topics:
            intelligence_topics = await OpportunityIntelligenceService(self.db).seed_topics(channel_id=channel_id, limit=8)
        effective_seed_topics = seed_topics or intelligence_topics
        ideas = self.strategy.generate(channel=channel_ctx, memory=memory, seed_topics=effective_seed_topics, count=len(slots), goal=goal)

        plan = ContentPlan(
            channel_id=channel.id,
            name=name,
            start_date=start_date,
            end_date=start_date + timedelta(days=horizon_days - 1),
            timezone=tz_name,
            goal=goal,
            cadence_per_week=cadence_per_week,
            publish_time=publish_time,
            weekdays=sorted(set(weekdays or [slot.local_date.weekday() for slot in slots[:min(len(slots), 7)]])),
            production_lead_hours=production_lead_hours,
            auto_publish=auto_publish,
            status="DRAFT",
            settings={"seed_topics": effective_seed_topics, "explicit_seed_topics": seed_topics, "intelligence_seed_topics": intelligence_topics, "slot_count": len(slots)},
        )
        self.db.add(plan)
        await self.db.flush()

        for position, (slot, idea) in enumerate(zip(slots, ideas), start=1):
            idea_row = ContentIdea(
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
                rationale={**idea.rationale, "autopilot_plan_id": str(plan.id)},
                status="PLANNED",
                selected=False,
            )
            self.db.add(idea_row)
            await self.db.flush()
            production_start = slot.utc_datetime - timedelta(hours=production_lead_hours)
            item = ContentPlanItem(
                plan_id=plan.id,
                idea_id=idea_row.id,
                position=position,
                topic=idea.topic,
                title=idea.title,
                hook=idea.hook,
                angle=idea.angle,
                format="long_form",
                scheduled_for=slot.utc_datetime,
                production_start_at=production_start,
                status="PLANNED",
                metadata_json={
                    "goal": goal,
                    "scheduled_local": slot.local_datetime.isoformat(),
                    "timezone": tz_name,
                    "production_lead_hours": production_lead_hours,
                    "auto_publish": auto_publish,
                },
            )
            self.db.add(item)
            await self.db.flush()
            blueprint_spec = self.intelligence.build_blueprint(
                channel=channel_ctx,
                memory=memory,
                idea={"topic": idea.topic, "title": idea.title, "hook": idea.hook, "angle": idea.angle},
                goal=goal,
            )
            blueprint = ContentBlueprint(
                channel_id=channel.id,
                idea_id=idea_row.id,
                plan_item_id=item.id,
                format=blueprint_spec.format,
                hook_pattern=blueprint_spec.hook_pattern,
                target_duration_minutes=blueprint_spec.target_duration_minutes,
                visual_change_seconds=blueprint_spec.visual_change_seconds,
                narrative_structure={"sections": blueprint_spec.narrative_structure},
                packaging=blueprint_spec.packaging,
                experiment_spec=blueprint_spec.experiment_spec,
                reasoning=blueprint_spec.reasoning,
                confidence=blueprint_spec.confidence,
            )
            self.db.add(blueprint)
            await self.db.flush()
            item.format = blueprint_spec.format
            item.metadata_json = {
                **item.metadata_json,
                "content_intelligence": {
                    "blueprint_id": str(blueprint.id),
                    "hook_pattern": blueprint_spec.hook_pattern,
                    "target_duration_minutes": blueprint_spec.target_duration_minutes,
                    "visual_change_seconds": blueprint_spec.visual_change_seconds,
                    "experiment_dimension": blueprint_spec.experiment_spec.get("dimension"),
                    "confidence": blueprint_spec.confidence,
                },
            }
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def list_plans(self, channel_id: str, limit: int = 20) -> list[ContentPlan]:
        q = await self.db.execute(select(ContentPlan).where(ContentPlan.channel_id == uuid.UUID(channel_id)).order_by(ContentPlan.start_date.desc(), ContentPlan.created_at.desc()).limit(limit))
        return list(q.scalars().all())

    async def get_plan(self, channel_id: str, plan_id: str) -> tuple[ContentPlan, list[ContentPlanItem]]:
        plan = await self.db.get(ContentPlan, uuid.UUID(plan_id))
        if not plan or plan.channel_id != uuid.UUID(channel_id):
            raise ValueError("Plan not found")
        q = await self.db.execute(select(ContentPlanItem).where(ContentPlanItem.plan_id == plan.id).order_by(ContentPlanItem.position))
        return plan, list(q.scalars().all())

    async def activate(self, channel_id: str, plan_id: str) -> ContentPlan:
        plan, _ = await self.get_plan(channel_id, plan_id)
        if plan.status in {"CANCELLED", "COMPLETED"}:
            raise ValueError(f"Plan cannot be activated from {plan.status}")
        plan.status = "ACTIVE"
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def pause(self, channel_id: str, plan_id: str) -> ContentPlan:
        plan, _ = await self.get_plan(channel_id, plan_id)
        if plan.status == "COMPLETED":
            raise ValueError("Completed plans cannot be paused")
        plan.status = "PAUSED"
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def materialize_items(self, channel_id: str, plan_id: str, item_ids: list[str] | None = None) -> list[ContentPlanItem]:
        plan, items = await self.get_plan(channel_id, plan_id)
        selected_ids = {uuid.UUID(x) for x in item_ids} if item_ids else None
        created: list[ContentPlanItem] = []
        for item in items:
            if selected_ids is not None and item.id not in selected_ids:
                continue
            if item.project_id or item.status in {"CANCELLED", "COMPLETED"}:
                continue
            project = VideoProject(channel_id=plan.channel_id, topic=item.topic, data={
                "plan_id": str(plan.id),
                "plan_item_id": str(item.id),
                "idea_id": str(item.idea_id) if item.idea_id else None,
                "title": item.title,
                "hook": item.hook,
                "angle": item.angle,
                "schedule": {
                    "scheduled_for": item.scheduled_for.isoformat(),
                    "scheduled_local": item.metadata_json.get("scheduled_local"),
                    "timezone": plan.timezone,
                    "auto_publish": plan.auto_publish,
                    "privacy_status": "private",
                },
            })
            self.db.add(project)
            await self.db.flush()
            item.project_id = project.id
            item.status = "MATERIALIZED"
            created.append(item)
        await self.db.commit()
        return created

    async def summary(self, channel_id: str, plan_id: str) -> dict:
        plan, items = await self.get_plan(channel_id, plan_id)
        counts: dict[str, int] = {}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return {
            "id": str(plan.id), "name": plan.name, "status": plan.status,
            "start_date": plan.start_date.isoformat(), "end_date": plan.end_date.isoformat(),
            "timezone": plan.timezone, "goal": plan.goal, "cadence_per_week": plan.cadence_per_week,
            "publish_time": plan.publish_time, "auto_publish": plan.auto_publish,
            "production_lead_hours": plan.production_lead_hours,
            "total_items": len(items), "status_counts": counts,
        }

    async def process_due_items(self, now: datetime | None = None) -> int:
        now = now or datetime.utcnow()
        q = await self.db.execute(
            select(ContentPlanItem, ContentPlan, Channel)
            .join(ContentPlan, ContentPlan.id == ContentPlanItem.plan_id)
            .join(Channel, Channel.id == ContentPlan.channel_id)
            .where(
                ContentPlan.status == "ACTIVE",
                ContentPlanItem.status.in_({"PLANNED", "MATERIALIZED"}),
                ContentPlanItem.production_start_at <= now,
            )
            .order_by(ContentPlanItem.production_start_at.asc())
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        raw_rows = list(q.all())
        if not raw_rows:
            return 0

        # Portfolio-aware weighted fairness: overdue slots still take precedence, while
        # channels with lower spend relative to their budget weight are preferred when several
        # slots are due at the same time. This prevents one busy channel from monopolising workers.
        from sqlalchemy import func
        from app.models.portfolio import CostEvent, PortfolioChannel
        month_start = datetime(now.year, now.month, 1)
        channel_ids = {channel.id for _, _, channel in raw_rows}
        spend_rows = await self.db.execute(
            select(CostEvent.channel_id, func.coalesce(func.sum(CostEvent.total_cost_usd), 0))
            .where(CostEvent.channel_id.in_(channel_ids), CostEvent.created_at >= month_start)
            .group_by(CostEvent.channel_id)
        )
        spend_by_channel = {channel_id: float(spend or 0) for channel_id, spend in spend_rows.all()}
        link_rows = await self.db.execute(select(PortfolioChannel).where(PortfolioChannel.channel_id.in_(channel_ids), PortfolioChannel.active.is_(True)))
        weight_by_channel = {row.channel_id: max(0.1, row.budget_weight) for row in link_rows.scalars().all()}
        rows = sorted(raw_rows, key=lambda row: (
            row[0].production_start_at > now,
            row[0].production_start_at,
            spend_by_channel.get(row[2].id, 0.0) / weight_by_channel.get(row[2].id, 1.0),
            str(row[2].id),
        ))[:20]
        count = 0
        from app.db.session import SessionLocal
        from app.workflows.engine import WorkflowEngine
        engine = WorkflowEngine(SessionLocal)
        for item, plan, channel in rows:
            # Claim the slot before leaving this transaction so another scheduler
            # cannot enqueue the same item concurrently.
            item.status = "ENQUEUING"
            if not item.project_id:
                project = VideoProject(channel_id=plan.channel_id, topic=item.topic, data={
                    "plan_id": str(plan.id), "plan_item_id": str(item.id), "idea_id": str(item.idea_id) if item.idea_id else None,
                    "title": item.title, "hook": item.hook, "angle": item.angle,
                    "schedule": {"scheduled_for": item.scheduled_for.isoformat(), "scheduled_local": item.metadata_json.get("scheduled_local"), "timezone": plan.timezone, "auto_publish": plan.auto_publish, "privacy_status": "private"},
                })
                self.db.add(project)
                await self.db.flush()
                item.project_id = project.id
            project_id = item.project_id
            await self.db.commit()
            try:
                key = f"autopilot:{plan.id}:{item.id}"
                await engine.create_or_get(project_id, key)
            except Exception as exc:
                async with self.db.begin():
                    current = await self.db.get(ContentPlanItem, item.id)
                    if current:
                        current.status = "PLANNED"
                        current.error_message = str(exc)
                continue
            async with self.db.begin():
                current = await self.db.get(ContentPlanItem, item.id)
                if current:
                    current.status = "QUEUED"
                    current.error_message = None
            count += 1
        return count
