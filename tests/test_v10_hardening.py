from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_failed_projects_use_checkpoint_resume():
    text = (ROOT / "app/api/routes.py").read_text()
    assert "use /retry to resume from the last successful checkpoint" in text


def test_workflow_cancel_endpoint_exists():
    text = (ROOT / "app/api/workflows.py").read_text()
    assert '@router.post("/{workflow_id}/cancel")' in text
    assert 'run.status = "CANCELLED"' in text


def test_orchestrator_checks_cancellation_between_steps():
    text = (ROOT / "app/services/orchestrator.py").read_text()
    assert 'if workflow.status == "CANCELLED"' in text


def test_worker_does_not_turn_cancellation_into_failure():
    text = (ROOT / "app/workflows/engine.py").read_text()
    assert 'current.status == "CANCELLED"' in text


def test_frontend_exposes_workflow_cancel_action():
    text = (ROOT / "frontend/app/projects/[id]/page.tsx").read_text()
    assert "Cancel workflow" in text
    assert "/api/v1/workflows/${workflowId}/cancel" in text
