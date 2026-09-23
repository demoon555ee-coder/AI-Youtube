from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v26_integration_dependencies_and_ci_matrix():
    integration = (ROOT / "requirements-integration.txt").read_text()
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "testcontainers[postgres]" in integration
    assert "pytest-asyncio" in (ROOT / "requirements-dev.txt").read_text()
    assert "postgres-version: ['15', '16']" in ci
    assert "python-version: ['3.12', '3.13']" in ci
    assert "  integration:" in ci
    assert "./scripts/run_integration_tests.sh" in ci
    assert "needs: [backend, frontend, integration, staging_e2e" in ci


def test_v26_sandbox_and_oauth_harnesses_do_not_print_secrets():
    yt = (ROOT / "scripts/youtube_api_sandbox_check.py").read_text()
    oauth = (ROOT / "scripts/youtube_oauth_live_check.py").read_text()
    assert "www.googleapis.com/youtube/v3/videos" in yt
    assert "read_only=true" in yt
    assert "oauth_token_values_not_printed=true" in oauth
    assert "credentials.token" not in oauth
    assert "refresh_token" not in oauth


def test_v26_provider_and_postgres_contract_files_exist():
    assert (ROOT / "tests/test_provider_contracts.py").exists()
    assert (ROOT / "tests/test_youtube_upload_contract.py").exists()
    assert (ROOT / "tests/integration/test_postgres_real.py").exists()


def test_current_compose_defaults_target_current_release():
    assert "4.2.4" in (ROOT / "docker-compose.yml").read_text()
    assert "4.2.4" in (ROOT / "docker-compose.production.yml").read_text()
