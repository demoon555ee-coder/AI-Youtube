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
