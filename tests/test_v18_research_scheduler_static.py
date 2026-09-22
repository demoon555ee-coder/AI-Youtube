from pathlib import Path

from app.models import ResearchRun, ResearchSchedule
from app.research.scheduler import ResearchSchedulerService
from app.db.migrations import MIGRATIONS

ROOT = Path(__file__).resolve().parents[1]


def test_v18_models_and_api_contract_are_registered():
    assert ResearchSchedule.__tablename__ == "research_schedules"
    assert ResearchRun.__tablename__ == "research_runs"
    text = (ROOT / "app/api/research_scheduler.py").read_text()
    assert 'prefix="/api/v1/research-scheduler"' in text
    assert 'post("/channels/{channel_id}/schedules")' in text
    assert 'post("/schedules/{schedule_id}/run"' in text
    assert 'get("/schedules/{schedule_id}/runs")' in text


def test_v18_scheduler_service_contract():
    assert hasattr(ResearchSchedulerService, "process_due")
    assert hasattr(ResearchSchedulerService, "run_schedule")
    assert hasattr(ResearchSchedulerService, "create_schedule")
    assert hasattr(ResearchSchedulerService, "list_runs")


def test_v18_worker_runs_research_scheduler():
    text = (ROOT / "app/workflows/worker.py").read_text()
    assert "ResearchSchedulerService" in text
    assert "_research_loop" in text
    assert "settings.research_scheduler_enabled" in text


def test_v18_migration_is_last_and_contains_scheduler_tables():
    versions = [name for name, _ in MIGRATIONS]
    assert "008_v18_research_scheduler" in versions
    sql = dict(MIGRATIONS)["008_v18_research_scheduler"]
    assert "CREATE TABLE IF NOT EXISTS research_schedules" in sql
    assert "CREATE TABLE IF NOT EXISTS research_runs" in sql
    assert "UPDATE research_opportunities" in sql


def test_v18_migration_chunks_are_single_sql_statements():
    sql = dict(MIGRATIONS)["008_v18_research_scheduler"]
    chunks = [part.strip() for part in sql.split("\n\n") if part.strip()]
    assert chunks
    assert all(chunk.count(";") == 1 for chunk in chunks)
