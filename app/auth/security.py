from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID
from hmac import compare_digest

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.auth import ApiKey, AuthSession, Membership, Organization, User
from app.oauth.crypto import decrypt, encrypt

PASSWORD_ITERATIONS = 310_000
DEV_ORGANIZATION_KEY = "local-user"
ROLE_PERMISSIONS = {
    "owner": {"*", "admin:manage"},
    "admin": {"*", "admin:manage"},
    "editor": {"read", "content:write", "publish", "research:write", "analytics:read"},
    "analyst": {"read", "analytics:read", "research:write"},
    "viewer": {"read", "analytics:read"},
}


async def auth_db_dependency():
    # Lazy import keeps security helpers importable in offline/unit-test environments.
    from app.db.session import SessionLocal
    async with SessionLocal() as db:
        yield db


@dataclass(frozen=True)
class Principal:
    user_id: UUID | None
    organization_id: UUID | None
    role: str
    auth_type: str
    token_id: UUID | None
    scope_key: str
    scopes: frozenset[str] = frozenset({"*"})

    @property
    def is_dev_fallback(self) -> bool:
        return self.auth_type == "dev-fallback"


def _hash_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _new_token(prefix: str) -> tuple[str, str]:
    raw = f"{prefix}_{secrets.token_urlsafe(42)}"
    return raw, _hash_secret(raw)


async def get_or_create_dev_organization(db: AsyncSession) -> Organization:
    row = await db.scalar(select(Organization).where(Organization.slug == "local-dev"))
    if row:
        return row
    row = Organization(name="Local Development", slug="local-dev")
    db.add(row)
    await db.flush()
    return row


async def _resolve_membership(db: AsyncSession, user_id: UUID, organization_id: str | None) -> tuple[str, UUID]:
    if organization_id:
        try:
            org_uuid = UUID(organization_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid organization id") from exc
        membership = await db.scalar(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.organization_id == org_uuid,
                Membership.active.is_(True),
            )
        )
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        return membership.role, membership.organization_id
    membership = await db.scalar(
        select(Membership)
        .where(Membership.user_id == user_id, Membership.active.is_(True))
        .order_by(Membership.created_at.asc())
    )
    if not membership:
        raise HTTPException(status_code=403, detail="User has no active organization")
    return membership.role, membership.organization_id


async def resolve_principal(request: Request, db: AsyncSession) -> Principal:
    authorization = request.headers.get("Authorization", "")
    cookie_credential = request.cookies.get(settings.auth_cookie_name, "")
    organization_header = request.headers.get("X-Organization-Id")

    credential = ""
    if authorization:
        scheme, _, candidate = authorization.partition(" ")
        if scheme.lower() != "bearer" or not candidate:
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        credential = candidate
    elif cookie_credential:
        credential = cookie_credential
    else:
        if settings.app_env != "production" and settings.auth_dev_fallback:
            return Principal(None, None, "owner", "dev-fallback", None, DEV_ORGANIZATION_KEY, frozenset({"*"}))
        raise HTTPException(status_code=401, detail="Authentication required")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if credential.startswith("sess_"):
        token_hash = _hash_secret(credential)
        session = await db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
            )
        )
        if not session or session.expires_at <= now:
            raise HTTPException(status_code=401, detail="Session expired or revoked")
        user = await db.get(User, session.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User is inactive")
        role, organization_id = await _resolve_membership(db, user.id, organization_header)
        session.last_seen_at = now
        await db.commit()
        return Principal(user.id, organization_id, role, "session", session.id, str(organization_id), frozenset({"*"}))

    if credential.startswith("key_"):
        token_hash = _hash_secret(credential)
        api_key = await db.scalar(
            select(ApiKey).where(
                ApiKey.key_hash == token_hash,
                ApiKey.revoked_at.is_(None),
            )
        )
        if not api_key or (api_key.expires_at and api_key.expires_at <= now):
            raise HTTPException(status_code=401, detail="API key expired or revoked")
        user = await db.get(User, api_key.created_by_user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="API key owner is inactive")
        role, organization_id = await _resolve_membership(db, user.id, str(api_key.organization_id))
        api_key.last_used_at = now
        await db.commit()
        return Principal(user.id, organization_id, role, "api-key", api_key.id, str(organization_id), frozenset(api_key.scopes or []))

    raise HTTPException(status_code=401, detail="Unknown bearer credential")


async def enforce_csrf(request: Request, db: AsyncSession, principal: Principal) -> None:
    """Enforce synchronizer-token CSRF protection for browser sessions on state changes."""
    if principal.auth_type != "session" or request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("Origin")
    if origin and origin not in settings.allowed_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")
    if not principal.token_id:
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    session = await db.get(AuthSession, principal.token_id)
    if not session or not session.csrf_token_enc:
        raise HTTPException(status_code=403, detail="CSRF token unavailable")
    provided = request.headers.get(settings.csrf_token_header, "")
    try:
        expected = decrypt(session.csrf_token_enc)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="CSRF validation failed") from exc
    if not provided or not compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def get_current_principal(request: Request, db: AsyncSession = Depends(auth_db_dependency)) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return principal
    principal = await resolve_principal(request, db)
    request.state.principal = principal
    return principal


async def require_permission(request: Request, db: AsyncSession, permission: str) -> Principal:
    principal = await get_current_principal(request, db)
    permissions = ROLE_PERMISSIONS.get(principal.role, set())
    if principal.auth_type == "api-key" and "*" not in principal.scopes and permission not in principal.scopes:
        raise HTTPException(status_code=403, detail="API key scope does not allow this action")
    if "*" not in permissions and permission not in permissions:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return principal


def permission_dependency(permission: str):
    async def dependency(request: Request, db: AsyncSession = Depends(auth_db_dependency)) -> Principal:
        return await require_permission(request, db, permission)

    return dependency


def require_roles(roles: Iterable[str]):
    allowed = set(roles)

    async def dependency(request: Request, db: AsyncSession = Depends(auth_db_dependency)) -> Principal:
        principal = await get_current_principal(request, db)
        if principal.role not in allowed and principal.role != "owner":
            raise HTTPException(status_code=403, detail="Insufficient role")
        return principal

    return dependency


def issue_session_csrf_token(session: AuthSession) -> str:
    raw, _ = _new_token("csrf")
    session.csrf_token_enc = encrypt(raw)
    return raw


async def create_session(db: AsyncSession, user_id: UUID, ttl_days: int = 30) -> tuple[AuthSession, str, str]:
    raw, digest = _new_token("sess")
    session = AuthSession(
        user_id=user_id,
        token_hash=digest,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=ttl_days),
    )
    issue_session_csrf_token(session)
    db.add(session)
    await db.flush()
    return session, raw, session_csrf_token(session)


def session_csrf_token(session: AuthSession) -> str:
    if not session.csrf_token_enc:
        raise RuntimeError("Session CSRF token is not configured")
    return decrypt(session.csrf_token_enc)


def verify_password(password: str, encoded: str) -> bool:
    return _verify_password(password, encoded)


def hash_password(password: str) -> str:
    return _hash_password(password)


def issue_api_key() -> tuple[str, str, str]:
    raw, digest = _new_token("key")
    prefix = raw[:16]
    return raw, digest, prefix
