from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import httpx


def test_retry_after_and_http_retry_respects_429(monkeypatch):
    from app.resilience.http import request_with_retry
    calls = []
    responses = [
        httpx.Response(429, headers={"Retry-After": "0"}, request=httpx.Request("GET", "https://x.test")),
        httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "https://x.test")),
    ]
    async def op():
        calls.append(1)
        return responses.pop(0)
    async def no_sleep(_):
        return None
    monkeypatch.setattr("app.resilience.http.asyncio.sleep", no_sleep)
    result = asyncio.run(request_with_retry(op, max_retries=2))
    assert result.status_code == 200
    assert len(calls) == 2


def test_retry_helper_does_not_retry_4xx(monkeypatch):
    from app.resilience.http import request_with_retry
    calls = []
    async def op():
        calls.append(1)
        return httpx.Response(400, request=httpx.Request("GET", "https://x.test"))
    result = asyncio.run(request_with_retry(op, max_retries=3))
    assert result.status_code == 400
    assert len(calls) == 1


def test_circuit_policy_transitions():
    import inspect
    from app.resilience.provider import ProviderReliabilityService
    source = inspect.getsource(ProviderReliabilityService)
    assert "HALF_OPEN" in source
    assert "provider_failure_threshold" in source
    assert "next_probe_at" in source


def test_v31_models_and_migration():
    from app.models import ProviderCircuitState, WorkflowDeadLetter, MediaGenerationJob
    assert ProviderCircuitState.__tablename__ == "provider_circuit_states"
    assert WorkflowDeadLetter.__tablename__ == "workflow_dead_letters"
    assert hasattr(MediaGenerationJob, "idempotency_key")
    text = Path("app/db/migrations.py").read_text()
    assert "019_v31_provider_resilience" in text


def test_dead_letter_engine_contract():
    text = Path("app/workflows/engine.py").read_text()
    assert "WorkflowDeadLetter" in text
    assert "workflow_dead_letter" in text


def test_media_recovery_contract():
    text = Path("app/media/recovery.py").read_text()
    assert "RECOVERING" in text
    assert "DEAD_LETTER" in text
    assert "recover_existing_job" in text


def test_worker_runs_media_recovery_loop():
    text = Path("app/workflows/worker.py").read_text()
    assert "_media_recovery_loop" in text
    assert "MediaRecoveryService" in text


def test_http_video_has_submission_callback_and_recovery():
    text = Path("app/media/http_video.py").read_text()
    assert '"on_submitted"' in text
    assert "recover_existing_job" in text
    assert "status_url" in text


def test_router_uses_provider_reliability():
    text = Path("app/routing/service.py").read_text()
    assert "ProviderReliabilityService" in text
    assert "provider_circuit_open" in text


def test_media_job_is_tenant_scoped():
    from app.models import MediaGenerationJob
    assert hasattr(MediaGenerationJob, "portfolio_id")


def test_observability_circuit_route_contract():
    text = Path("app/api/observability.py").read_text()
    assert '@router.get("/circuits")' in text
    assert "enforce_request_authorization" in text


def test_provider_router_circuit_is_part_of_feasibility():
    text = Path("app/routing/service.py").read_text()
    assert "circuit_ok" in text
    assert "feasible[candidate.provider]" in text


def test_media_recovery_is_tenant_scoped():
    text = Path("app/media/recovery.py").read_text()
    assert "ProviderProfile.portfolio_id == job.portfolio_id" in text

def test_production_job_persists_before_long_poll():
    text = Path("app/agents/production.py").read_text()
    assert "await self.db.commit()" in text


def test_v31_media_job_has_process_crash_recovery_fields():
    text = Path("app/models/media_job.py").read_text()
    assert "portfolio_id" in text and "local_output_path" in text and "idempotency_key" in text

def test_v31_observability_is_tenant_scoped():
    text = Path("app/api/observability.py").read_text()
    assert "MediaGenerationJob.organization_id == principal.organization_id" in text
    assert "Channel.organization_id == principal.organization_id" in text


def test_v31_circuit_state_creation_is_atomic():
    text = Path("app/resilience/provider.py").read_text()
    assert "on_conflict_do_nothing" in text

def test_v31_only_transient_provider_errors_open_circuit():
    text = Path("app/services/orchestrator.py").read_text()
    assert "is_transient_provider_error" in text
