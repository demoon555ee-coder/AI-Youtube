from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_is_database_backed_and_resumable():
    text = (ROOT / "app/workflows/engine.py").read_text()
    assert "with_for_update(skip_locked=True)" in text
    assert "lease_until" in text
    assert "idempotency_key" in text
    assert "run_project(str(workflow.project_id), workflow_id=str(workflow.id))" in text


def test_workflow_has_checkpoints_and_events():
    text = (ROOT / "app/models/workflow.py").read_text()
    assert "class WorkflowStep" in text
    assert "output_data" in text
    assert "class WorkflowEvent" in text
    assert "BigInteger" in text


def test_sse_endpoint_exists():
    text = (ROOT / "app/api/workflows.py").read_text()
    assert 'media_type="text/event-stream"' in text
    assert "WorkflowEvent.id > cursor" in text


def test_api_uses_workflow_queue_not_fastapi_background_tasks():
    text = (ROOT / "app/api/routes.py").read_text()
    assert "BackgroundTasks" not in text
    assert "WorkflowEngine(SessionLocal).create_or_get" in text
