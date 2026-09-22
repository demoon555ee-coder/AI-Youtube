from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.research_graph import ResearchOpportunity
from app.models.research_scheduler import ResearchRun, ResearchSchedule
from app.research.graph_service import opportunity_fingerprint
from app.research.scheduler import advance_next_run_at, backoff_hours, normalize_utc_naive, serialize_run, serialize_schedule


def test_opportunity_fingerprint_is_stable_and_case_insensitive():
    a = opportunity_fingerprint(" AI Agents ", "Why AI agents matter")
    b = opportunity_fingerprint("ai agents", "why ai agents matter")
    assert a == b
    assert len(a) == 64


def test_scheduler_catch_up_policy():
    now = datetime(2026, 9, 18, 12, 0)
    previous = datetime(2026, 9, 18, 2, 0)
    assert advance_next_run_at(previous, now, 4, False) == datetime(2026, 9, 18, 16, 0)
    assert advance_next_run_at(previous, now, 4, True) == datetime(2026, 9, 18, 14, 0)


def test_scheduler_normalizes_timezone_aware_input_to_utc():
    value = datetime(2026, 9, 18, 18, 0, tzinfo=timezone(timedelta(hours=2)))
    assert normalize_utc_naive(value) == datetime(2026, 9, 18, 16, 0)


def test_scheduler_backoff_is_bounded_by_cadence():
    assert backoff_hours(1, 24) == 2
    assert backoff_hours(4, 24) == 16
    assert backoff_hours(8, 6) == 6


def test_scheduler_serializers_expose_operational_state():
    now = datetime(2026, 9, 18, 12, 0)
    schedule = ResearchSchedule(
        id="00000000-0000-0000-0000-000000000001",
        channel_id="00000000-0000-0000-0000-000000000002",
        name="Daily AI",
        query="AI agents",
        next_run_at=now,
    )
    payload = serialize_schedule(schedule)
    assert payload["name"] == "Daily AI"
    assert payload["enabled"] is True
    assert "failure_count" in payload

    run = ResearchRun(
        id="00000000-0000-0000-0000-000000000003",
        schedule_id=schedule.id,
        channel_id=schedule.channel_id,
        query="AI agents",
    )
    run_payload = serialize_run(run)
    assert run_payload["status"] == "RUNNING"
    assert run_payload["trigger_type"] == "scheduled"


def test_research_opportunity_model_has_deduplication_fields():
    assert ResearchOpportunity.__tablename__ == "research_opportunities"
    assert hasattr(ResearchOpportunity, "fingerprint")
    assert hasattr(ResearchOpportunity, "occurrence_count")
    assert hasattr(ResearchOpportunity, "last_seen_at")
