from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password, verify_password
from app.config import settings
from app.models import ApiKey, AuditLog, AuthSession, LoginRateLimit, Membership, PrivacyRequest, UsageEvent, User
from app.services.audit import redact_sensitive

LOGIN_WINDOW_MINUTES = 15
LOGIN_MAX_FAILURES = 5
LOGIN_BLOCK_MINUTES = 15


def client_ip(request) -> str:
    trusted = max(0, int(settings.trusted_proxy_count))
    if trusted and request.headers.get("x-forwarded-for"):
        parts = [p.strip() for p in request.headers["x-forwarded-for"].split(",") if p.strip()]
        if parts:
            return parts[0]
    return request.client.host if request.client else "unknown"


def rate_limit_key(email: str, ip: str) -> str:
    return hashlib.sha256(f"login:{email.strip().lower()}:{ip}".encode()).hexdigest()


async def login_is_allowed(db: AsyncSession, *, email: str, ip: str) -> tuple[bool, int]:
    now = datetime.utcnow()
    key = rate_limit_key(email, ip)
    row = await db.get(LoginRateLimit, key)
    if not row:
        return True, 0
    if row.blocked_until and row.blocked_until > now:
        return False, max(1, int((row.blocked_until - now).total_seconds()))
    if now - row.window_started_at >= timedelta(minutes=LOGIN_WINDOW_MINUTES):
        row.window_started_at = now
        row.failure_count = 0
        row.blocked_until = None
    return True, 0


async def record_login_failure(db: AsyncSession, *, email: str, ip: str) -> None:
    now = datetime.utcnow()
    key = rate_limit_key(email, ip)
    row = await db.get(LoginRateLimit, key, with_for_update=True)
    if row is None:
        row = LoginRateLimit(key_hash=key, window_started_at=now, failure_count=1)
        db.add(row)
        try:
            await db.flush()
            return
        except IntegrityError:
            await db.rollback()
            row = await db.get(LoginRateLimit, key, with_for_update=True)
            if row is None:
                return
    if now - row.window_started_at >= timedelta(minutes=LOGIN_WINDOW_MINUTES):
        row.window_started_at = now
        row.failure_count = 1
        row.blocked_until = None
    else:
        row.failure_count += 1
    if row.failure_count >= LOGIN_MAX_FAILURES:
        row.blocked_until = now + timedelta(minutes=LOGIN_BLOCK_MINUTES)
    await db.flush()


async def clear_login_failures(db: AsyncSession, *, email: str, ip: str) -> None:
    await db.execute(delete(LoginRateLimit).where(LoginRateLimit.key_hash == rate_limit_key(email, ip)))


async def create_deletion_request(db: AsyncSession, *, user_id: UUID, organization_id: UUID | None, reason: str | None) -> PrivacyRequest:
    active = await db.scalar(
        select(PrivacyRequest).where(
            PrivacyRequest.user_id == user_id,
            PrivacyRequest.request_type == "ERASURE",
            PrivacyRequest.status.in_(("REQUESTED", "PROCESSING")),
        ).order_by(PrivacyRequest.created_at.desc())
    )
    if active:
        return active
    row = PrivacyRequest(
        organization_id=organization_id,
        user_id=user_id,
        request_type="ERASURE",
        reason=(reason or "").strip()[:2000] or None,
        metadata_json={"scope": "personal_identity_and_credentials"},
    )
    db.add(row)
    await db.flush()
    return row


async def process_deletion_request(db: AsyncSession, request_id: UUID) -> PrivacyRequest | None:
    row = await db.get(PrivacyRequest, request_id, with_for_update=True)
    if not row or row.status == "COMPLETED":
        return row
    if row.request_type != "ERASURE" or not row.user_id:
        row.status = "COMPLETED"
        row.completed_at = datetime.utcnow()
        await db.flush()
        return row

    row.status = "PROCESSING"
    user = await db.get(User, row.user_id, with_for_update=True)
    if user:
        user.is_active = False
        user.email = f"deleted-{user.id}@example.invalid"
        user.name = "Deleted User"
        user.password_hash = hash_password(secrets.token_urlsafe(24))
        user.anonymized_at = datetime.utcnow()

        await db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked_at=datetime.utcnow()))
        await db.execute(update(ApiKey).where(ApiKey.created_by_user_id == user.id).values(revoked_at=datetime.utcnow()))
        await db.execute(update(Membership).where(Membership.user_id == user.id).values(active=False))
        await db.execute(update(AuditLog).where(AuditLog.actor_user_id == user.id).values(actor_user_id=None))
        await db.execute(update(UsageEvent).where(UsageEvent.user_id == user.id).values(user_id=None))

    row.status = "COMPLETED"
    row.completed_at = datetime.utcnow()
    await db.flush()
    return row


async def build_user_export(db: AsyncSession, *, user_id: UUID) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    memberships_q = await db.execute(
        select(Membership,).where(Membership.user_id == user_id).order_by(Membership.created_at.asc())
    )
    sessions_q = await db.execute(select(AuthSession).where(AuthSession.user_id == user_id).order_by(AuthSession.created_at.desc()).limit(settings.privacy_export_max_events))
    keys_q = await db.execute(select(ApiKey).where(ApiKey.created_by_user_id == user_id).order_by(ApiKey.created_at.desc()).limit(settings.privacy_export_max_events))
    audits_q = await db.execute(select(AuditLog).where(AuditLog.actor_user_id == user_id).order_by(AuditLog.created_at.desc()).limit(settings.privacy_export_max_events))
    usage_q = await db.execute(select(UsageEvent).where(UsageEvent.user_id == user_id).order_by(UsageEvent.created_at.desc()).limit(settings.privacy_export_max_events))
    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "created_at": user.created_at,
        },
        "memberships": [{"organization_id": str(m.organization_id), "role": m.role, "active": m.active, "created_at": m.created_at} for m in memberships_q.scalars().all()],
        "sessions": [{"id": str(s.id), "expires_at": s.expires_at, "last_seen_at": s.last_seen_at, "revoked_at": s.revoked_at, "created_at": s.created_at} for s in sessions_q.scalars().all()],
        "api_keys": [{"id": str(k.id), "name": k.name, "prefix": k.prefix, "scopes": k.scopes, "expires_at": k.expires_at, "last_used_at": k.last_used_at, "revoked_at": k.revoked_at} for k in keys_q.scalars().all()],
        "audit_events": [{"id": a.id, "action": a.action, "resource_type": a.resource_type, "resource_id": a.resource_id, "created_at": a.created_at, "metadata": redact_sensitive(a.metadata_json)} for a in audits_q.scalars().all()],
        "usage_events": [{"id": str(u.id), "service": u.service, "action": u.action, "units": u.units, "unit": u.unit, "estimated_cost_usd": u.estimated_cost_usd, "created_at": u.created_at, "metadata": redact_sensitive(u.metadata_json)} for u in usage_q.scalars().all()],
    }


async def run_retention_cleanup(db: AsyncSession) -> dict:
    now = datetime.utcnow()
    audit_cutoff = now - timedelta(days=settings.audit_retention_days)
    usage_cutoff = now - timedelta(days=settings.usage_retention_days)
    session_cutoff = now - timedelta(days=settings.auth_session_retention_days)
    rate_cutoff = now - timedelta(days=settings.login_rate_limit_retention_days)
    privacy_cutoff = now - timedelta(days=settings.privacy_request_retention_days)
    deleted = {}
    for name, stmt in {
        "audit_logs": delete(AuditLog).where(AuditLog.created_at < audit_cutoff),
        "usage_events": delete(UsageEvent).where(UsageEvent.created_at < usage_cutoff),
        "auth_sessions": delete(AuthSession).where(AuthSession.revoked_at.is_not(None), AuthSession.revoked_at < session_cutoff),
        "login_rate_limits": delete(LoginRateLimit).where(LoginRateLimit.updated_at < rate_cutoff),
        "privacy_requests": delete(PrivacyRequest).where(PrivacyRequest.status == "COMPLETED", PrivacyRequest.completed_at.is_not(None), PrivacyRequest.completed_at < privacy_cutoff),
    }.items():
        result = await db.execute(stmt)
        deleted[name] = result.rowcount or 0
    await db.flush()
    return deleted
