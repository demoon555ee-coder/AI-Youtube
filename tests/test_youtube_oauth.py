import json

from app.config import settings
from app.services.youtube_oauth import _normalized_client_config, oauth_client_credentials


def test_google_oauth_accepts_env_json(monkeypatch):
    payload = {
        "web": {
            "client_id": "env-client-id",
            "client_secret": "env-client-secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    monkeypatch.setattr(settings, "google_client_secrets_json", json.dumps(payload))
    monkeypatch.setattr(settings, "google_client_secrets_file", "/does/not/exist.json")

    config = _normalized_client_config()

    assert config["web"]["client_id"] == "env-client-id"
    assert oauth_client_credentials() == ("env-client-id", "env-client-secret")


def test_google_oauth_env_json_takes_precedence(monkeypatch, tmp_path):
    file_path = tmp_path / "client_secret.json"
    file_path.write_text(
        json.dumps({
            "web": {
                "client_id": "file-client-id",
                "client_secret": "file-client-secret",
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "google_client_secrets_file", str(file_path))
    monkeypatch.setattr(settings, "google_client_secrets_json", json.dumps({
        "web": {
            "client_id": "env-client-id",
            "client_secret": "env-client-secret",
        }
    }))

    assert oauth_client_credentials() == ("env-client-id", "env-client-secret")


def test_google_oauth_falls_back_to_file(monkeypatch, tmp_path):
    file_path = tmp_path / "client_secret.json"
    file_path.write_text(
        json.dumps({
            "web": {
                "client_id": "file-client-id",
                "client_secret": "file-client-secret",
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "google_client_secrets_file", str(file_path))
    monkeypatch.setattr(settings, "google_client_secrets_json", "")

    assert oauth_client_credentials() == ("file-client-id", "file-client-secret")
