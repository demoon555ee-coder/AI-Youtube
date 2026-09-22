from datetime import date
import pytest
from app.autopilot.service import build_schedule_slots, parse_hhmm


def test_parse_hhmm():
    assert parse_hhmm("18:30").hour == 18
    with pytest.raises(ValueError):
        parse_hhmm("18-30")


def test_schedule_30_days_three_per_week_default_days_are_unique():
    slots = build_schedule_slots(start_date=date(2026, 9, 21), horizon_days=30, timezone_name="UTC", publish_time="18:00", cadence_per_week=3)
    assert 10 <= len(slots) <= 14
    assert len({s.local_date for s in slots}) == len(slots)


def test_schedule_respects_explicit_weekdays():
    slots = build_schedule_slots(start_date=date(2026, 9, 21), horizon_days=14, timezone_name="UTC", publish_time="18:00", cadence_per_week=2, weekdays=[1, 4])
    assert all(s.local_date.weekday() in {1, 4} for s in slots)
    assert [s.local_date.weekday() for s in slots] == [1, 4, 1, 4]


def test_schedule_timezone_converts_to_utc():
    slots = build_schedule_slots(start_date=date(2026, 1, 5), horizon_days=1, timezone_name="Europe/Brussels", publish_time="18:00", cadence_per_week=1, weekdays=[0])
    assert slots[0].utc_datetime.hour == 17


def test_timezone_dst_changes_offset():
    winter = build_schedule_slots(start_date=date(2026, 1, 5), horizon_days=1, timezone_name="Europe/Brussels", publish_time="18:00", cadence_per_week=1, weekdays=[0])[0]
    summer = build_schedule_slots(start_date=date(2026, 7, 6), horizon_days=1, timezone_name="Europe/Brussels", publish_time="18:00", cadence_per_week=1, weekdays=[0])[0]
    assert winter.utc_datetime.hour == 17
    assert summer.utc_datetime.hour == 16


def test_weekday_validation():
    with pytest.raises(ValueError):
        build_schedule_slots(start_date=date(2026, 1, 5), horizon_days=7, timezone_name="UTC", publish_time="18:00", cadence_per_week=2, weekdays=[7])


def test_weekday_count_cannot_exceed_cadence():
    with pytest.raises(ValueError):
        build_schedule_slots(start_date=date(2026, 1, 5), horizon_days=7, timezone_name="UTC", publish_time="18:00", cadence_per_week=1, weekdays=[0, 1])


def test_horizon_is_bounded():
    with pytest.raises(ValueError):
        build_schedule_slots(start_date=date(2026, 1, 5), horizon_days=366, timezone_name="UTC", publish_time="18:00", cadence_per_week=1)


def test_explicit_weekdays_must_match_cadence():
    with pytest.raises(ValueError):
        build_schedule_slots(start_date=date(2026, 1, 5), horizon_days=14, timezone_name="UTC", publish_time="18:00", cadence_per_week=3, weekdays=[0, 2])


def test_schedule_cross_year_boundary():
    slots = build_schedule_slots(start_date=date(2026, 12, 28), horizon_days=10, timezone_name="UTC", publish_time="18:00", cadence_per_week=2, weekdays=[0, 3])
    assert slots[0].local_date == date(2026, 12, 28)
    assert slots[-1].local_date == date(2027, 1, 4)


def test_naive_schedule_is_serialized_as_utc_without_timezone():
    slots = build_schedule_slots(start_date=date(2026, 3, 2), horizon_days=1, timezone_name="UTC", publish_time="00:30", cadence_per_week=1, weekdays=[0])
    assert slots[0].utc_datetime.isoformat() == "2026-03-02T00:30:00"
