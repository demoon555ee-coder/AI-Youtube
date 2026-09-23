import json
from json import JSONDecodeError
from pathlib import Path

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _read_client_config() -> dict:
    raw_json = settings.google_client_secrets_json.strip()
    if raw_json:
        try:
            raw = json.loads(raw_json)
        except JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_CLIENT_SECRETS_JSON contains invalid JSON") from exc
    else:
        try:
            raw = json.loads(Path(settings.google_client_secrets_file).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError("Google OAuth client secret configuration is missing") from exc

    if not isinstance(raw, dict):
        raise RuntimeError("Google OAuth client secret configuration must be a JSON object")
    return raw


def _normalized_client_config() -> dict:
    raw = _read_client_config()
    if raw.get("web") or raw.get("installed"):
        return raw
    if raw.get("client_id") and raw.get("client_secret"):
        return {"web": raw}
    raise RuntimeError("Google OAuth client secret configuration is missing client_id/client_secret")


def build_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(
        _normalized_client_config(),
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
    config = _normalized_client_config().get("web") or _normalized_client_config().get("installed")
    if not isinstance(config, dict) or not config.get("client_id") or not config.get("client_secret"):
        raise RuntimeError("Google OAuth client secret configuration is missing client_id/client_secret")
    return str(config["client_id"]), str(config["client_secret"])
