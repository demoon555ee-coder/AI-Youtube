from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def test_google_auth_contract_and_account_selector():
    service = (ROOT / "app/services/google_auth.py").read_text(encoding="utf-8")
    api = (ROOT / "app/api/auth.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend/app/login/page.tsx").read_text(encoding="utf-8")
    assert '"openid"' in service
    assert '"https://www.googleapis.com/auth/userinfo.email"' in service
    assert '"https://www.googleapis.com/auth/userinfo.profile"' in service
    assert 'prompt="select_account consent"' in service
    assert '@router.post("/google/start")' in api
    assert '@router.get("/google/callback")' in api
    assert '"/api/v1/auth/google/start"' in frontend


def test_google_oauth_syncs_channel_collection():
    client = (ROOT / "app/services/youtube_client.py").read_text(encoding="utf-8")
    service = (ROOT / "app/services/youtube_service.py").read_text(encoding="utf-8")
    auth = (ROOT / "app/api/auth.py").read_text(encoding="utf-8")
    assert "def get_mine_channels" in client
    assert '"maxResults": 50' in client
    assert "get_mine_channels(creds)" in service
    assert "get_mine_channels(creds)" in auth
    assert '"channel_count": len(linked)' in auth
    assert 'channel_sync_failed = True' in auth
    assert '"unavailable" if channel_sync_failed' in auth


def test_google_identity_can_have_no_youtube_channel(monkeypatch):
    from app.services import youtube_client

    request = Mock()
    request.execute.return_value = {"items": []}
    service = Mock()
    service.channels.return_value.list.return_value = request
    monkeypatch.setattr(youtube_client, "youtube_data_api", lambda _credentials: service)

    assert youtube_client.get_mine_channels(object()) == []


def test_google_channel_sync_reads_every_page(monkeypatch):
    from app.services import youtube_client

    first = Mock()
    first.execute.return_value = {"items": [{"id": "channel-1"}], "nextPageToken": "page-2"}
    second = Mock()
    second.execute.return_value = {"items": [{"id": "channel-2"}]}
    service = Mock()
    service.channels.return_value.list.side_effect = [first, second]
    monkeypatch.setattr(youtube_client, "youtube_data_api", lambda _credentials: service)

    assert youtube_client.get_mine_channels(object()) == [{"id": "channel-1"}, {"id": "channel-2"}]
    assert service.channels.return_value.list.call_count == 2
    assert service.channels.return_value.list.call_args_list[1].kwargs["pageToken"] == "page-2"


def test_google_oauth_allows_http_only_for_local_development(monkeypatch):
    from app.services import google_auth

    monkeypatch.setattr(google_auth.settings, "public_base_url", "http://localhost:8000")
    monkeypatch.setattr(google_auth.settings, "google_auth_redirect_path", "/api/v1/auth/google/callback")
    monkeypatch.setattr(google_auth.settings, "app_env", "development")
    monkeypatch.setenv("OAUTHLIB_INSECURE_TRANSPORT", "0")

    google_auth.build_flow("test-state")

    assert google_auth.os.environ["OAUTHLIB_INSECURE_TRANSPORT"] == "1"


def test_google_oauth_rejects_http_outside_local_development(monkeypatch):
    from app.services import google_auth

    monkeypatch.setattr(google_auth.settings, "public_base_url", "http://localhost:8000")
    monkeypatch.setattr(google_auth.settings, "google_auth_redirect_path", "/api/v1/auth/google/callback")
    monkeypatch.setattr(google_auth.settings, "app_env", "production")

    try:
        google_auth.build_flow("test-state")
    except RuntimeError as exc:
        assert "localhost development" in str(exc)
    else:
        raise AssertionError("Production must reject HTTP OAuth callbacks")
