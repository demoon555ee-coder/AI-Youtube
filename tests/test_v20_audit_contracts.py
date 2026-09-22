from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_worker_bootstraps_migrations_and_keeps_postproduction_session_live():
    text = (ROOT / "app/workflows/worker.py").read_text()
    assert "from app.db.migrations import apply_migrations" in text
    assert "await apply_migrations(engine)" in text
    engine_text = (ROOT / "app/workflows/engine.py").read_text()
    assert "await Orchestrator(db).run_project" in engine_text
    assert "await auto_publish_if_due(db, workflow.project_id)" in engine_text


def test_production_error_handling_is_registered():
    text = (ROOT / "app/main.py").read_text()
    assert 'version=settings.app_version' in text
    assert '@app.exception_handler(Exception)' in text
    assert 'APP_ENCRYPTION_KEY is required in production' in text


def test_v20_ui_and_audit_runner_exist():
    assert (ROOT / "frontend/app/opportunity-intelligence/page.tsx").exists()
    assert (ROOT / "scripts/full_audit.py").exists()
