from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

from app.config import settings

GOOGLE_AUTH_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _client_config() -> dict:
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
    if raw.get("web") or raw.get("installed"):
        return raw
    if raw.get("client_id") and raw.get("client_secret"):
        return {"web": raw}
    raise RuntimeError("Google OAuth client secret configuration is missing client_id/client_secret")


def build_flow(state: str | None = None) -> Flow:
    flow = Flow.from_client_config(_client_config(), scopes=GOOGLE_AUTH_SCOPES, state=state)
    flow.redirect_uri = settings.google_auth_redirect_uri
    return flow
def authorization_url(state: str) -> str:
    flow = build_flow(state)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
    )
    return url


def exchange_code(callback_url: str, state: str):
    flow = build_flow(state)
    flow.fetch_token(authorization_response=callback_url)
    return flow.credentials


def verified_identity(credentials) -> dict:
    token = credentials.id_token
    if not token:
        raise RuntimeError("Google identity token was not returned")
    client = (_client_config().get("web") or _client_config().get("installed") or {})
    client_id = client.get("client_id")
    if not client_id:
        raise RuntimeError("Google OAuth client id is missing")
    payload = id_token.verify_oauth2_token(token, Request(), client_id)
    if payload.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise RuntimeError("Invalid Google identity issuer")
    email = str(payload.get("email") or "").strip().lower()
    if not email or not payload.get("email_verified"):
        raise RuntimeError("A verified Google email is required")
    return {
        "sub": str(payload.get("sub") or ""),
        "email": email,
        "name": str(payload.get("name") or "").strip(),
        "picture": str(payload.get("picture") or "").strip(),
    }
