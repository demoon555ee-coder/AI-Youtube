from __future__ import annotations
import os

from pathlib import Path

import yaml

from app.config import settings
from app.deployment import validate_production_settings, LATEST_SCHEMA_VERSION
from app.db.migrations import MIGRATIONS

ROOT = Path(__file__).resolve().parents[1]


def test_version_and_schema_gate_are_current():
    assert settings.app_version.startswith(("3.", "4."))
    assert LATEST_SCHEMA_VERSION == MIGRATIONS[-1][0]


def test_dev_configuration_is_valid_for_local_use():
    assert validate_production_settings() == []


def test_production_compose_has_migration_gate_and_restart_policy():
    data = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
    assert data["services"]["migrate"]["command"] == ["python", "scripts/migrate.py"]
    assert data["services"]["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert data["services"]["worker"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert data["services"]["api"]["restart"] == "unless-stopped"
    assert data["services"]["worker"]["restart"] == "unless-stopped"

def test_staging_migration_bootstraps_base_schema_explicitly():
    data = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
    env = data["services"]["migrate"]["environment"]
    assert env["MIGRATION_ONLY"] == "true"
    assert env["MIGRATION_BOOTSTRAP_BASE_SCHEMA"] == "true"
    script = (ROOT / "scripts/migrate.py").read_text()
    assert "MIGRATION_BOOTSTRAP_BASE_SCHEMA" in script
    assert "Base.metadata.create_all" in script
    assert "CREATE ROLE anon" in script
    assert "CREATE ROLE authenticated" in script

def test_staging_media_uses_shared_named_volume():
    data = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
    for service in ("api", "worker"):
        assert "staging_output:/app/data/output" in data["services"][service]["volumes"]
    assert "staging_output" in data["volumes"]

def test_thumbnail_endpoint_has_canonical_file_fallback():
    source = (ROOT / "app/api/routes.py").read_text(encoding="utf-8")
    assert '"/thumbnail.png"' in source
    assert "settings.output_dir" in source


def test_project_page_shows_thumbnail_for_ready_projects():
    source = (ROOT / "frontend/app/projects/[id]/page.tsx").read_text(encoding="utf-8")
    assert 'project.status === "READY_TO_PUBLISH"' in source
    assert 'alt="Generated thumbnail"' in source


def test_staging_web_api_host_matches_browser_origin():
    data = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
    web = data["services"]["web"]
    assert web["build"]["args"]["NEXT_PUBLIC_API_BASE"] == "http://127.0.0.1:8001"
    assert web["environment"]["NEXT_PUBLIC_API_BASE"] == "http://127.0.0.1:8001"


def test_backend_image_runs_as_non_root_and_has_healthcheck():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "useradd --system --uid 10001" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_frontend_image_has_healthcheck_and_lockfile_fallback():
    dockerfile = (ROOT / "frontend/Dockerfile").read_text()
    assert "npm ci" in dockerfile
    assert "npm install" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_release_scripts_are_present_and_executable():
    for name in ("deploy_release.sh", "rollback.sh"):
        path = ROOT / "scripts" / name
        assert path.exists()
        if os.name != "nt":
            assert path.stat().st_mode & 0o111


def test_ci_workflows_are_present():
    assert (ROOT / ".github/workflows/ci.yml").exists()
    assert (ROOT / ".github/workflows/deploy.yml").exists()


def test_schema_gate_is_part_of_readiness():
    main = (ROOT / "app/main.py").read_text()
    assert "schema_is_current(engine)" in main
    assert 'checks["schema"]' in main


def test_production_auto_migrate_disabled_in_compose():
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
    assert compose["services"]["api"]["environment"]["AUTO_MIGRATE"] == "false"
    assert compose["services"]["worker"]["environment"]["AUTO_MIGRATE"] == "false"


def test_authorization_has_settings_import():
    authz = (ROOT / "app/auth/authorization.py").read_text()
    assert "from app.config import settings" in authz


def test_metrics_are_private_by_default_in_production_compose():
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
    env_text = (ROOT / ".env.production.example").read_text()
    assert "METRICS_PUBLIC=false" in env_text
    assert "./secrets/metrics_token:/run/secrets/metrics_token:ro" in compose["services"]["prometheus"]["volumes"]


def test_deployment_has_backup_script_and_documented_schema_policy():
    assert (ROOT / "scripts/backup_database.sh").exists()
    docs = (ROOT / "deploy/DEPLOYMENT.md").read_text()
    assert "expand/contract" in docs
    assert "schema rollback is not automatic" in docs.lower()


def test_private_metrics_accept_bearer_token_path():
    access = (ROOT / "app/observability/access.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    prom = (ROOT / "deploy/prometheus.yml").read_text()
    assert "Authorization" in access and "bearer" in access
    assert "metrics_token_matches(request)" in main
    assert "authorization:" in prom
    assert "credentials_file: /run/secrets/metrics_token" in prom


def test_production_validator_rejects_unsafe_defaults(monkeypatch, tmp_path):
    from app.deployment import validate_production_settings
    from app.config import settings as runtime_settings
    secret_file = tmp_path / "client_secret.json"
    secret_file.write_text("{}")
    monkeypatch.setattr(runtime_settings, "app_env", "production")
    monkeypatch.setattr(runtime_settings, "app_encryption_key", "")
    monkeypatch.setattr(runtime_settings, "auth_dev_fallback", True)
    monkeypatch.setattr(runtime_settings, "public_base_url", "http://localhost:8000")
    monkeypatch.setattr(runtime_settings, "frontend_url", "http://localhost:3000")
    monkeypatch.setattr(runtime_settings, "cors_origins", "http://localhost:3000")
    monkeypatch.setattr(runtime_settings, "database_url", "postgresql+asyncpg://postgres:postgres@db:5432/youtube_ai")
    monkeypatch.setattr(runtime_settings, "google_client_secrets_file", str(secret_file))
    codes = {item.code for item in validate_production_settings()}
    assert {"missing_encryption_key", "dev_auth_enabled", "public_url_not_https", "frontend_url_not_https", "localhost_cors", "default_database_credentials"}.issubset(codes)


def test_metrics_token_helper_accepts_bearer_header(monkeypatch, tmp_path):
    from starlette.requests import Request
    from app.observability.access import metrics_token_matches
    from app.config import settings as runtime_settings
    token_file = tmp_path / "metrics_token"
    token_file.write_text("abc123\n")
    monkeypatch.setattr(runtime_settings, "metrics_auth_token_file", str(token_file))
    scope = {"type": "http", "method": "GET", "path": "/api/v1/metrics", "headers": [(b"authorization", b"Bearer abc123")], "query_string": b"", "server": ("test", 80), "scheme": "http", "client": ("test", 1)}
    assert metrics_token_matches(Request(scope)) is True
