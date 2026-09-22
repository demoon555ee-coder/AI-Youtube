from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_worker_is_separate_process():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "worker:" in compose
    assert '"app.workflows.worker"' in compose
    assert 'WORKFLOW_ENABLED: "false"' in compose


def test_retry_has_backoff_and_next_run_at():
    engine = (ROOT / "app/workflows/engine.py").read_text()
    model = (ROOT / "app/models/workflow.py").read_text()
    assert "next_run_at" in engine
    assert "2 ** max(retryable.attempts - 1, 0)" in engine
    assert "next_run_at" in model


def test_api_has_no_background_task_dependency():
    text = (ROOT / "app/api/routes.py").read_text()
    assert "BackgroundTasks" not in text
    assert "WorkflowEngine" in text
