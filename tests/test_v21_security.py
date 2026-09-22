from pathlib import Path
from uuid import uuid4

from app.auth.security import (
    PASSWORD_ITERATIONS,
    Principal,
    hash_password,
    issue_api_key,
    verify_password,
)
from app.auth.authorization import PUBLIC_SUFFIXES
from app.db.migrations import MIGRATIONS, _split_sql

ROOT = Path(__file__).resolve().parents[1]


def test_password_hashing_uses_salted_pbkdf2_and_never_plaintext():
    password = "A-very-strong-password-123"
    encoded = hash_password(password)
    assert encoded.startswith(f"pbkdf2_sha256${PASSWORD_ITERATIONS}$")
    assert encoded != password
    assert verify_password(password, encoded)
    assert not verify_password("wrong", encoded)
    assert hash_password(password) != hash_password(password)


def test_api_keys_are_unrecoverable_and_prefixed():
    raw, digest, prefix = issue_api_key()
    assert raw.startswith("key_")
    assert prefix == raw[:16]
    assert len(digest) == 64
    assert raw not in digest


def test_principal_scope_key_is_organization_not_actor_user():
    org_id = uuid4()
    user_id = uuid4()
    principal = Principal(user_id, org_id, "editor", "session", uuid4(), str(org_id))
    assert principal.scope_key == str(org_id)
    assert principal.scope_key != str(user_id)


def test_public_endpoints_are_small_and_explicit():
    assert "/api/v1/auth/register" in PUBLIC_SUFFIXES
    assert "/api/v1/auth/login" in PUBLIC_SUFFIXES
    assert "/api/v1/youtube/oauth/callback" in PUBLIC_SUFFIXES
    assert "/api/v1/projects" not in PUBLIC_SUFFIXES


def test_security_migration_is_last_and_contains_all_core_tables():
    versions = [v for v, _ in MIGRATIONS]
    assert versions == sorted(versions, key=lambda x: int(x.split("_", 1)[0]))
    assert "011_v21_saas_security" in versions
    sql = dict(MIGRATIONS)["011_v21_saas_security"]
    for table in ("users", "organizations", "memberships", "auth_sessions", "api_keys", "audit_logs", "usage_events"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "ALTER TABLE channels ADD COLUMN IF NOT EXISTS organization_id" in sql
    assert "ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS organization_id" in sql


def test_security_migration_splits_without_losing_json_default():
    sql = dict(MIGRATIONS)["011_v21_saas_security"]
    statements = _split_sql(sql)
    assert len(statements) >= 20
    assert any("DEFAULT '[\"read\"]'::jsonb" in statement for statement in statements)


def test_oauth_rejects_cross_tenant_channel_reassignment():
    text = (ROOT / "app/services/youtube_service.py").read_text()
    assert "must never be reassigned" in text
    assert "already connected to another organization" in text


def test_auth_routes_do_not_embed_secrets():
    text = (ROOT / "app/api/auth.py").read_text()
    assert '"api_key": raw' in text
    assert 'key_hash' not in text.split('return {', 1)[0]
    assert "password_hash" not in text


def test_global_tenant_guard_is_installed():
    main = (ROOT / "app/main.py").read_text()
    authz = (ROOT / "app/auth/authorization.py").read_text()
    assert "dependencies=[Depends(enforce_request_authorization)]" in main
    assert "Cross-organization owner_id is not allowed" in authz
    assert "Read-only API keys are denied all mutations" in authz


def test_frontend_auth_flow_is_present():
    assert (ROOT / "frontend/app/login/page.tsx").exists()
    api = (ROOT / "frontend/lib/api.ts").read_text()
    assert 'credentials: "include"' in api
    assert 'youtube_ai_auth_token' not in api
    assert 'credentials: "include"' in api
    assert 'youtube_ai_auth_token' not in api


def test_login_and_register_audit_actions_are_distinct():
    text = (ROOT / "app/api/auth.py").read_text()
    assert 'action="auth.register"' in text
    assert 'action="auth.login"' in text
    assert text.index('action="auth.register"') < text.index('action="auth.login"')


def test_admin_cannot_grant_owner_role():
    text = (ROOT / "app/api/auth.py").read_text()
    assert 'principal.role == "admin" and payload.role == "owner"' in text
    assert 'Admins cannot grant owner role' in text


def test_browser_auth_does_not_claim_to_return_a_bearer_token():
    text = (ROOT / "app/api/auth.py").read_text()
    assert '"auth_type": "cookie_session"' in text
    assert '"token_type": "bearer"' not in text
