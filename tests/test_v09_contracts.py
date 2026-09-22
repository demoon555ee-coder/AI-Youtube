from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_publish_uses_project_artifacts():
    text = (ROOT / "app/services/youtube_service.py").read_text()
    assert 'data.get("editor", {}).get("output_path")' in text
    assert 'data.get("thumbnail", {}).get("path")' in text


def test_oauth_callback_redirect_quotes_error_message():
    text = (ROOT / "app/api/youtube.py").read_text()
    assert "quote(str(exc)[:160])" in text


def test_access_token_refresh_is_persisted():
    text = (ROOT / "app/services/youtube_service.py").read_text()
    assert "_persist_refreshed_token(conn, creds)" in text
