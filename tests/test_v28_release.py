from __future__ import annotations

from pathlib import Path
import json
import os

import yaml

from app.config import settings
from app.db.migrations import MIGRATIONS

ROOT = Path(__file__).resolve().parents[1]


def test_v28_version_and_migration_are_current():
    assert settings.app_version.startswith(("3.", "4."))
    assert any(v.startswith("016_v28") for v, _ in MIGRATIONS)


def test_blue_green_compose_has_distinct_slots_and_external_network():
    data = yaml.safe_load((ROOT / "docker-compose.bluegreen.yml").read_text())
    services = data["services"]
    for name in ("api_blue", "api_green", "web_blue", "web_green"):
        assert name in services
    assert services["api_blue"]["ports"] == ["127.0.0.1:8002:8000"]
    assert services["api_green"]["ports"] == ["127.0.0.1:8003:8000"]
    assert data["networks"]["production_net"]["external"] is True


def test_release_scripts_are_present_and_executable():
    for name in ("deploy_blue_green.sh", "rollback_blue_green.sh", "switch_slot.sh", "verify_backup.sh", "restore_drill.sh"):
        path = ROOT / "scripts" / name
        assert path.exists()
        if os.name != "nt":
            assert path.stat().st_mode & 0o111


def test_release_manifest_tools_have_required_contracts():
    create = (ROOT / "scripts/create_release_manifest.py").read_text()
    verify = (ROOT / "scripts/verify_release_manifest.py").read_text()
    assert "youtube-ai-release-v2" in create
    assert "database_schema_rollback" in create
    assert "api_digest_pinned" in create and "web_digest_pinned" in create
    assert "manifest_verified=true" in verify
    assert "api_digest_pinned" in verify and "web_digest_pinned" in verify


def test_backup_has_checksum_and_restore_drill():
    backup = (ROOT / "scripts/backup_database.sh").read_text()
    drill = (ROOT / "scripts/restore_drill.sh").read_text()
    assert "sha256sum" in backup
    assert "gzip -t" in drill
    assert "schema_migrations" in drill


def test_deploy_has_pre_switch_validation_and_post_switch_smoke():
    deploy = (ROOT / "scripts/deploy_blue_green.sh").read_text()
    assert "verify_release_manifest.py" in deploy
    assert "health/ready" in deploy
    assert "switch_slot.sh" in deploy
    assert "PROXY_RELOAD_CMD" in deploy
    assert "PUBLIC_SMOKE_URL" in deploy


def test_rollback_is_application_only():
    rollback = (ROOT / "scripts/rollback_blue_green.sh").read_text()
    assert "migrate" not in rollback
    assert "switch_slot.sh" in rollback


def test_ci_contains_release_and_dr_backup_controls():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    deploy = (ROOT / ".github/workflows/deploy.yml").read_text()
    assert "restore_drill" in ci
    assert "RELEASE_MANIFEST" in ci
    assert "deploy_blue_green.sh" in deploy
    assert "rollback_blue_green.sh" in deploy
    assert "scp RELEASE_MANIFEST.json" in deploy


def test_release_history_migration_is_present():
    migration_text = (ROOT / "app/db/migrations.py").read_text()
    assert "016_v28_release_history" in migration_text
    assert "release_deployments" in migration_text


def test_docs_cover_blue_green_and_restore_drill():
    docs = (ROOT / "deploy/DEPLOYMENT.md").read_text()
    assert "blue/green" in docs.lower()
    assert "restore drill" in docs.lower()
    assert "database schema rollback" in docs.lower()


def test_release_workflow_is_present_and_immutable():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    assert "tags:" in workflow and "v*.*.*" in workflow
    assert "steps.api.outputs.digest" in workflow
    assert "steps.web.outputs.digest" in workflow
    assert "create_release_manifest.py" in workflow
    assert "steps.api.outputs.digest" in workflow and "steps.web.outputs.digest" in workflow


def test_compose_defaults_target_current_release():
    for fn in ("docker-compose.yml", "docker-compose.production.yml", "docker-compose.staging.yml"):
        text = (ROOT / fn).read_text()
        assert "2.7.0" not in text
        if fn == "docker-compose.production.yml":
            assert "4.2.1" in text
        elif fn != "docker-compose.bluegreen.yml":
            assert "4.2.1" in text


def test_switch_slot_requires_proxy_reload():
    text = (ROOT / "scripts/switch_slot.sh").read_text()
    assert "PROXY_RELOAD_CMD" in text
    assert "ALLOW_UNRELOADED_PROXY" in text


def test_production_compose_accepts_digest_pinned_image_refs():
    text = (ROOT / "docker-compose.production.yml").read_text()
    assert "API_IMAGE_REF" in text
    assert "WEB_IMAGE_REF" in text
