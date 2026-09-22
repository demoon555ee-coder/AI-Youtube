from pathlib import Path
import os
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_v27_staging_compose_has_full_app_stack_and_migration_gate():
    data = yaml.safe_load((ROOT / "docker-compose.staging.yml").read_text())
    assert set(data["services"]) == {"db", "migrate", "api", "worker", "web"}
    assert data["services"]["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert data["services"]["worker"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert data["services"]["web"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert data["services"]["db"]["healthcheck"]["test"][0] == "CMD-SHELL"


def test_v27_staging_env_disables_dev_fallback_and_uses_mock_safe_providers():
    env = (ROOT / ".env.staging.example").read_text()
    assert "AUTH_DEV_FALLBACK=false" in env
    assert "BILLING_PROVIDER=mock" in env
    assert "LLM_PROVIDER=mock" in env
    assert "RESEARCH_PROVIDER=mock" in env
    assert "TTS_PROVIDER=espeak" in env
    assert "VISUAL_PROVIDER=mock_png" in env


def test_v27_playwright_harness_exists_and_covers_rendered_artifact():
    assert (ROOT / "e2e/package.json").exists()
    assert (ROOT / "e2e/playwright.config.ts").exists()
    spec = (ROOT / "e2e/tests/app.spec.ts").read_text()
    assert "Create account" in spec
    assert "Run AI workflow" in spec
    assert "READY_TO_PUBLISH" in spec
    assert "video/mp4" in spec
    assert "Generated thumbnail" in spec


def test_v27_staging_scripts_are_executable():
    for name in ("staging_up.sh", "staging_down.sh", "staging_smoke.sh"):
        p = ROOT / "scripts" / name
        assert p.exists()
        if os.name != "nt":
            assert p.stat().st_mode & 0o111


def test_v27_ci_has_staging_e2e_stage():
    wf = ROOT / ".github/workflows/ci.yml"
    assert wf.exists()
    text = wf.read_text()
    assert "staging_e2e:" in text
    assert "docker-compose.staging.yml" in text
    assert "playwright install --with-deps chromium" in text
    assert "npm run test" in text


def test_v27_cross_origin_eventsource_sends_session_cookie():
    spec = (ROOT / "frontend/app/projects/[id]/page.tsx").read_text()
    assert 'new EventSource(' in spec
    assert 'withCredentials:true' in spec


def test_v27_frontend_builds_api_base_into_client_bundle():
    dockerfile = (ROOT / "frontend/Dockerfile").read_text()
    compose = (ROOT / "docker-compose.staging.yml").read_text()
    assert "ARG NEXT_PUBLIC_API_BASE" in dockerfile
    assert "ENV NEXT_PUBLIC_API_BASE=${NEXT_PUBLIC_API_BASE}" in dockerfile
    assert "NEXT_PUBLIC_API_BASE: http://localhost:8001" in compose


def test_v27_image_publish_is_gated_by_staging_e2e():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "staging_e2e:" in ci
    assert "needs: [backend, frontend, integration, staging_e2e" in ci


def test_v27_production_frontend_build_requires_public_api_variable():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "NEXT_PUBLIC_API_BASE: ${{ vars.NEXT_PUBLIC_API_BASE }}" in ci
    assert "NEXT_PUBLIC_API_BASE must use https in production" in ci


def test_v27_e2e_has_its_own_static_parser():
    assert (ROOT / "e2e/check_ast.mjs").exists()
    pkg = (ROOT / "e2e/package.json").read_text()
    assert '"typescript"' in pkg
