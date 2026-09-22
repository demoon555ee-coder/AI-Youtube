from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_v31_settings_contract():
    text = (ROOT / "app/config.py").read_text()
    assert 'provider_failure_threshold' in text
    assert 'media_recovery_enabled' in text

def test_v31_migration_and_models():
    mig = (ROOT / "app/db/migrations.py").read_text()
    assert '019_v31_provider_resilience' in mig
    assert '020_v32_quality_postpublish' in mig
    assert 'provider_circuit_states' in mig
    assert 'workflow_dead_letters' in mig
    assert 'portfolio_id UUID NULL REFERENCES portfolios' in mig

def test_v31_media_recovery_is_started_by_worker():
    text=(ROOT / "app/workflows/worker.py").read_text()
    assert 'MediaRecoveryService' in text and '_media_recovery_loop' in text

def test_v31_http_retry_policy_is_used_by_real_providers():
    files=['app/providers/http_llm.py','app/research/http_json.py','app/media/http_video.py','app/media/openai_image.py','app/tts/openai.py']
    for rel in files:
        assert 'request_with_retry' in (ROOT/rel).read_text(), rel


def test_v31_release_tooling_mentions_resilience_files():
    for rel in ["scripts/create_release_manifest.py", "scripts/verify_release_manifest.py"]:
        text = (ROOT / rel).read_text()
        assert "app/resilience/provider.py" in text
        assert "app/media/recovery.py" in text

def test_v31_full_audit_includes_resilience_section():
    text = (ROOT / "scripts/full_audit.py").read_text()
    assert "def resilience_audit" in text
    assert "'resilience': resilience_audit()" in text
