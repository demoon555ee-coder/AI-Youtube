from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_compose_has_web_service_at_top_level():
    text = (ROOT / "docker-compose.yml").read_text()
    assert "  web:\n" in text
    assert text.rstrip().endswith("volumes:\n  pgdata:")
    assert "    build: ./frontend" in text


def test_publish_schema_does_not_accept_server_file_paths():
    text = (ROOT / "app/schemas/youtube.py").read_text()
    assert "video_path" not in text
    assert "thumbnail_path" not in text


def test_analytics_query_keeps_video_dimension():
    text = (ROOT / "app/services/youtube_client.py").read_text()
    assert 'dimensions="day,video"' in text


def test_frontend_calls_async_project_run_with_live_updates():
    text = (ROOT / "frontend/app/projects/[id]/page.tsx").read_text()
    assert 'new EventSource' in text
    assert '`/api/v1/projects/${id}/run`' in text



def test_stock_media_contract_is_present_and_attribution_is_preserved():
    provider = (ROOT / "app/media/pexels.py").read_text()
    factory = (ROOT / "app/media/factory.py").read_text()
    router = (ROOT / "app/routing/service.py").read_text()
    service = (ROOT / "app/media/service.py").read_text()

    assert "class PexelsPhotoProvider" in provider
    assert "class PexelsVideoProvider" in provider
    assert "PEXELS_API_KEY" in provider
    assert "PexelsPhotoProvider" in factory
    assert "PexelsVideoProvider" in factory
    assert '"pexels_video"' in router
    assert '"stock_broll": True' in router
    assert '"attribution": result.get("attribution")' in service


def test_generation_routing_cannot_select_stock_provider():
    router = (ROOT / "app/routing/service.py").read_text()

    assert '"stock": True' in router
    assert '"stock_broll": True' in router
    assert '"generative": True' in router
    assert '("production", "visual", 5, {"image", "generative"})' in router
    assert '("production_video", "video", 5, {"video", "generative"})' in router
    assert '("thumbnail", "image", 1, {"image", "generative"})' in router



def test_routing_runtime_availability_is_redacted_and_visible_in_ui():
    api = (ROOT / "app/api/routing.py").read_text()
    page = (ROOT / "frontend/app/routing/page.tsx").read_text()
    start = api.index('@router.get("/runtime-availability")')
    end = api.index('@router.get("/decisions")', start)
    block = api[start:end]
    assert '"runtime_available": candidate.runtime_available' in block
    assert '"api_key"' not in block
    assert '"/api/v1/routing/runtime-availability"' in page
    assert "Runtime availability" in page



def test_dashboard_refreshes_workflow_state_and_pipeline_matches_eight_stages():
    page = (ROOT / "frontend/app/page.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/app/globals.css").read_text(encoding="utf-8")
    assert 'window.setInterval(() => { void load(); }, 5000)' in page
    assert 'return () => window.clearInterval(timer);' in page
    assert '.pipeline { display:grid; grid-template-columns:repeat(8,1fr);' in css


def test_application_version_matches_current_changelog_release():
    import re
    config = (ROOT / "app/config.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    app_version = re.search(r'app_version: str = "([^"]+)"', config).group(1)
    changelog_version = re.search(r'^## ([0-9]+\\.[0-9]+\\.[0-9]+) — ', changelog, re.MULTILINE).group(1)
    assert app_version == changelog_version
    assert f"# YouTube AI Platform v{app_version}" in (ROOT / "README.md").read_text(encoding="utf-8")
