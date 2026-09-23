from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_google_auth_contract_and_account_selector():
    service = (ROOT / "app/services/google_auth.py").read_text(encoding="utf-8")
    api = (ROOT / "app/api/auth.py").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend/app/login/page.tsx").read_text(encoding="utf-8")
    assert '"openid"' in service
    assert '"email"' in service
    assert 'prompt="select_account consent"' in service
    assert '@router.post("/google/start")' in api
    assert '@router.get("/google/callback")' in api
    assert '"/api/v1/auth/google/start"' in frontend


def test_google_oauth_syncs_channel_collection():
    client = (ROOT / "app/services/youtube_client.py").read_text(encoding="utf-8")
    service = (ROOT / "app/services/youtube_service.py").read_text(encoding="utf-8")
    auth = (ROOT / "app/api/auth.py").read_text(encoding="utf-8")
    assert "def get_mine_channels" in client
    assert "maxResults=50" in client
    assert "get_mine_channels(creds)" in service
    assert "get_mine_channels(creds)" in auth
    assert '"channel_count": len(linked)' in auth
