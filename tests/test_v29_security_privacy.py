from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4

from app.auth.security import session_csrf_token
from app.config import settings
from app.db.migrations import MIGRATIONS
from app.oauth.crypto import decrypt, encrypt, generate_key
from app.privacy.service import (
    LOGIN_BLOCK_MINUTES,
    LOGIN_MAX_FAILURES,
    LOGIN_WINDOW_MINUTES,
    rate_limit_key,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v29_migration_is_last_and_contains_security_tables():
    versions = [v for v, _ in MIGRATIONS]
    assert versions == sorted(versions, key=lambda x: int(x.split("_", 1)[0]))
    sql = dict(MIGRATIONS)["017_v29_security_privacy"]
    assert "csrf_token_enc" in sql
    assert "privacy_requests" in sql
    assert "login_rate_limits" in sql
    assert "anonymized_at" in sql


def test_csrf_token_is_encrypted_and_round_trips(monkeypatch):
    current = generate_key()
    monkeypatch.setattr(settings, "app_encryption_key", current)
    monkeypatch.setattr(settings, "app_encryption_key_previous", "")
    raw = "csrf_" + "x" * 32
    session = SimpleNamespace(csrf_token_enc=encrypt(raw))
    assert session_csrf_token(session) == raw
    assert decrypt(session.csrf_token_enc) == raw


def test_encryption_rotation_supports_previous_key(monkeypatch):
    old_key = generate_key()
    new_key = generate_key()
    monkeypatch.setattr(settings, "app_encryption_key", old_key)
    monkeypatch.setattr(settings, "app_encryption_key_previous", "")
    ciphertext = encrypt("youtube-refresh-token")
    monkeypatch.setattr(settings, "app_encryption_key", new_key)
    monkeypatch.setattr(settings, "app_encryption_key_previous", old_key)
    assert decrypt(ciphertext) == "youtube-refresh-token"


def test_login_rate_limit_key_is_stable_and_non_reversible():
    key1 = rate_limit_key("USER@example.com", "203.0.113.10")
    key2 = rate_limit_key("user@example.com", "203.0.113.10")
    assert key1 == key2
    assert len(key1) == 64
    assert "example.com" not in key1
    assert LOGIN_WINDOW_MINUTES > 0
    assert LOGIN_MAX_FAILURES >= 3
    assert LOGIN_BLOCK_MINUTES >= LOGIN_WINDOW_MINUTES


def test_production_settings_require_secure_cookie_and_explicit_origins():
    deployment = (ROOT / "app/deployment.py").read_text()
    assert 'weak_auth_cookie_name' in deployment
    assert 'wildcard_cors' in deployment
    assert 'billing_return_url_not_https' in deployment


def test_csrf_defense_is_present_on_state_changing_browser_requests():
    security = (ROOT / "app/auth/security.py").read_text()
    authz = (ROOT / "app/auth/authorization.py").read_text()
    assert "async def enforce_csrf" in security
    assert "Origin not allowed" in security
    assert "compare_digest" in security
    assert "await enforce_csrf(request, db, principal)" in authz


def test_frontend_attaches_csrf_header_and_backend_exposes_token_endpoint():
    api = (ROOT / "frontend/lib/api.ts").read_text()
    auth = (ROOT / "app/api/auth.py").read_text()
    assert 'headers["X-CSRF-Token"]' in api
    assert 'api/v1/auth/csrf' in api
    assert '@router.get("/csrf")' in auth


def test_security_headers_are_configured_on_api_and_frontend():
    main = (ROOT / "app/main.py").read_text()
    next_config = (ROOT / "frontend/next.config.ts").read_text()
    for value in ["Content-Security-Policy", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"]:
        assert value in main
        assert value in next_config


def test_privacy_export_does_not_expose_credential_material():
    service = (ROOT / "app/privacy/service.py").read_text()
    export_body = service.split("async def build_user_export", 1)[1].split("async def run_retention_cleanup", 1)[0]
    assert "password_hash" not in export_body
    assert "token_hash" not in export_body
    assert "key_hash" not in export_body
    assert "api_keys" in export_body and "prefix" in export_body


def test_privacy_apis_require_authenticated_principal_and_reauth_for_erasure():
    text = (ROOT / "app/api/privacy.py").read_text()
    assert 'prefix="/api/v1/privacy"' in text
    assert 'Depends(get_current_principal)' in text
    assert 'verify_password(payload.password' in text
    assert '@router.get("/export")' in text
    assert '@router.post("/deletion-request")' in text
    assert '@router.post("/requests/{request_id}/cancel")' in text


def test_retention_and_rotation_are_wired_into_maintenance():
    config = (ROOT / "app/config.py").read_text()
    worker = (ROOT / "app/workflows/worker.py").read_text()
    script = (ROOT / "scripts/rotate_encryption_keys.py").read_text()
    assert "audit_retention_days" in config
    assert "run_retention_cleanup" in worker
    assert "rotate" in script
    assert "No plaintext credential values are printed" in script


def test_production_cookie_uses_host_prefix_example():
    env = (ROOT / ".env.production.example").read_text()
    assert "AUTH_COOKIE_NAME=__Host-youtube_ai_session" in env
    assert "APP_ENCRYPTION_KEY_PREVIOUS=" in env


def test_models_and_worker_include_privacy_types():
    models = (ROOT / "app/models/__init__.py").read_text()
    auth = (ROOT / "app/models/auth.py").read_text()
    privacy = (ROOT / "app/models/privacy.py").read_text()
    assert "PrivacyRequest" in models and "LoginRateLimit" in models
    assert "csrf_token_enc" in auth
    assert "class PrivacyRequest" in privacy
    assert "class LoginRateLimit" in privacy


def test_release_manifest_rotation_script_is_executable():
    path = ROOT / "scripts/rotate_encryption_keys.py"
    assert path.exists()
    if os.name != "nt":
        assert path.stat().st_mode & 0o111


def test_audit_metadata_has_central_secret_redaction_policy():
    text = (ROOT / "app/services/audit.py").read_text()
    assert "SENSITIVE_KEYS" in text
    assert '"[REDACTED]"' in text
    assert "metadata_json=redact_sensitive" in text
    assert "_normalize_key" in text


def test_registration_does_not_reveal_email_existence():
    text = (ROOT / "app/services/auth_service.py").read_text()
    assert 'Unable to create account' in text
    assert 'already exists' not in text


def test_audit_redaction_handles_nested_and_camel_case_secret_keys():
    from app.services.audit import redact_sensitive

    payload = {"accessToken": "secret", "nested": {"client_secret": "secret2", "safe": "ok"}}
    sanitized = redact_sensitive(payload)
    assert sanitized["accessToken"] == "[REDACTED]"
    assert sanitized["nested"]["client_secret"] == "[REDACTED]"
    assert sanitized["nested"]["safe"] == "ok"


def test_ci_release_audit_does_not_depend_on_itself():
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    block = text.split("\n  release_audit:", 1)[1].split("\n  images:", 1)[0]
    assert "needs: [backend, frontend, integration, staging_e2e]" in block
    assert "release_audit]" not in block
