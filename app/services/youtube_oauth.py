import json
from pathlib import Path

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def build_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_secrets_file(
        settings.google_client_secrets_file,
        scopes=SCOPES,
        state=state,
    )
    flow.redirect_uri = settings.oauth_redirect_uri
    return flow


def authorization_url(state: str) -> str:
    flow = build_flow(state)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return url


def exchange_code(callback_url: str, state: str) -> Credentials:
    flow = build_flow(state)
    flow.fetch_token(authorization_response=callback_url)
    return flow.credentials


def oauth_client_credentials() -> tuple[str, str]:
    raw = json.loads(Path(settings.google_client_secrets_file).read_text(encoding="utf-8"))
    config = raw.get("web") or raw.get("installed") or raw
    return str(config["client_id"]), str(config["client_secret"])
