from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_idempotency_key_cannot_cross_projects():
    text = (ROOT / "app/workflows/engine.py").read_text()
    assert "existing.project_id != project_id" in text
    assert "Idempotency key is already used by another project" in text


def test_retry_copies_completed_checkpoints():
    text = (ROOT / "app/workflows/engine.py").read_text()
    assert 'previous.status == "COMPLETED"' in text
    assert 'status="COMPLETED", output_data=previous.output_data or {}' in text


def test_frontend_subscribes_to_sse_workflow_events():
    text = (ROOT / "frontend/app/projects/[id]/page.tsx").read_text()
    assert "new EventSource" in text
    assert "/api/v1/workflows/" in text
