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
    planner = (ROOT / "app/routing/service.py").read_text()
    planner_service = (ROOT / "app/planner/service.py").read_text()

    assert '"stock": True' in router
    assert '"stock_broll": True' in router
    assert '"generative": True' in router
    assert '("production", "visual", 5, {"image", "generative"})' in planner_service
    assert '("production_video", "video", 5, {"video", "generative"})' in planner_service
    assert '("thumbnail", "image", 1, {"image", "generative"})' in planner_service
