from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, permission_dependency, session_csrf_token, issue_session_csrf_token
from app.config import settings
from app.db.session import get_db
from app.models.auth import ApiKey, AuditLog, AuthSession, Membership, Organization, User, UsageEvent
from app.schemas.auth import ApiKeyCreateRequest, LoginRequest, MemberAddRequest, OrganizationCreateRequest, RegisterRequest, UsageEventRequest
from app.services.audit import write_audit
from app.services.auth_service import add_member, create_key, login, record_usage, register
from app.privacy.service import create_deletion_request, build_user_export, client_ip, login_is_allowed, record_login_failure, clear_login_failures

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_payload(user: User) -> dict:
    return {"id": str(user.id), "email": user.email, "name": user.name, "is_active": user.is_active}


@router.post("/register")
async def auth_register(payload: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        user, org, membership, session, token, csrf_token = await register(
            db,
            email=str(payload.email),
            password=payload.password,
            name=payload.name,
            organization_name=payload.organization_name,
        )
        response.set_cookie(key=settings.auth_cookie_name, value=token, max_age=settings.auth_session_ttl_days * 86400, httponly=True, secure=settings.app_env == "production", samesite="lax", path="/")
        # CSRF token is returned only over the authenticated TLS channel and kept in memory by the SPA.

        await write_audit(db, Principal(user.id, org.id, membership.role, "session", session.id, str(org.id), frozenset({"*"})), request, action="auth.register", resource_type="user", resource_id=str(user.id))
        await db.commit()
        return {
            "auth_type": "cookie_session",
            "csrf_token": csrf_token,
            "expires_at": session.expires_at,
            "user": _user_payload(user),
            "organization": {"id": str(org.id), "name": org.name, "slug": org.slug, "role": membership.role},
        }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/login")
async def auth_login(payload: LoginRequest, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    email = str(payload.email)
    ip = client_ip(request)
    allowed, retry_after = await login_is_allowed(db, email=email, ip=ip)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many failed login attempts", headers={"Retry-After": str(retry_after)})
    try:
        user, membership, session, token, csrf_token = await login(
            db,
            email=email,
            password=payload.password,
            organization_id=payload.organization_id,
        )
        await clear_login_failures(db, email=email, ip=ip)
        org = await db.get(Organization, membership.organization_id)
        response.set_cookie(key=settings.auth_cookie_name, value=token, max_age=settings.auth_session_ttl_days * 86400, httponly=True, secure=settings.app_env == "production", samesite="lax", path="/")
        await write_audit(db, Principal(user.id, org.id, membership.role, "session", session.id, str(org.id), frozenset({"*"})), request, action="auth.login", resource_type="user", resource_id=str(user.id))
        await db.commit()
        return {
            "auth_type": "cookie_session",
            "csrf_token": csrf_token,
            "expires_at": session.expires_at,
            "user": _user_payload(user),
            "organization": {"id": str(org.id), "name": org.name, "slug": org.slug, "role": membership.role} if org else None,
        }
    except ValueError as exc:
        await record_login_failure(db, email=email, ip=ip)
        await db.commit()
        raise HTTPException(401, "Invalid email or password") from exc


@router.post("/logout")
async def auth_logout(request: Request, response: Response, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.token_id and principal.auth_type == "session":
        session = await db.get(AuthSession, principal.token_id)
        if session:
            session.revoked_at = datetime.utcnow()
    await write_audit(db, request, principal, action="auth.logout", resource_type="session", resource_id=str(principal.token_id) if principal.token_id else None)
    response = Response(content='{"ok":true}', media_type="application/json")
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    await db.commit()
    return response


@router.get("/csrf")
async def csrf_token(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.auth_type != "session" or not principal.token_id:
        return {"csrf_token": None}
    session = await db.get(AuthSession, principal.token_id)
    if not session:
        raise HTTPException(401, "Session not found")
    if not session.csrf_token_enc:
        issue_session_csrf_token(session)
        await db.commit()
    return {"csrf_token": session_csrf_token(session)}


@router.get("/me")
async def auth_me(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.is_dev_fallback:
        return {"user": {"id": None, "email": "local-dev", "name": "Local Development"}, "organization": None, "role": "owner", "auth_type": "dev-fallback"}
    user = await db.get(User, principal.user_id)
    org = await db.get(Organization, principal.organization_id)
    return {"user": _user_payload(user), "organization": {"id": str(org.id), "name": org.name, "slug": org.slug} if org else None, "role": principal.role, "auth_type": principal.auth_type}


@router.get("/organizations")
async def auth_organizations(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.user_id is None:
        return {"organizations": []}
    rows = await db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.organization_id == Organization.id)
        .where(Membership.user_id == principal.user_id, Membership.active.is_(True))
        .order_by(Organization.name.asc())
    )
    return {"organizations": [{"id": str(org.id), "name": org.name, "slug": org.slug, "role": role} for org, role in rows.all()]}


@router.post("/organizations")
async def create_organization(payload: OrganizationCreateRequest, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    if principal.user_id is None or principal.organization_id is None:
        raise HTTPException(400, "Authenticated user and organization are required")
    from app.services.auth_service import unique_slug
    org = Organization(name=payload.name.strip(), slug=await unique_slug(db, payload.name))
    db.add(org)
    await db.flush()
    db.add(Membership(user_id=principal.user_id, organization_id=org.id, role="owner", active=True))
    await write_audit(db, request, principal, action="organization.create", resource_type="organization", resource_id=str(org.id))
    await db.commit()
    return {"id": str(org.id), "name": org.name, "slug": org.slug, "role": "owner"}


@router.get("/organizations/{organization_id}/members")
async def list_members(organization_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.organization_id != organization_id:
        raise HTTPException(403, "Organization access denied")
    rows = await db.execute(
        select(User, Membership).join(Membership, Membership.user_id == User.id).where(Membership.organization_id == organization_id, Membership.active.is_(True)).order_by(User.email.asc())
    )
    return {"members": [{"user_id": str(user.id), "email": user.email, "name": user.name, "role": membership.role} for user, membership in rows.all()]}


@router.post("/organizations/{organization_id}/members")
async def add_org_member(organization_id: UUID, payload: MemberAddRequest, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    if principal.organization_id != organization_id or principal.role not in {"owner", "admin"}:
        raise HTTPException(403, "Admin role required")
    if principal.role == "admin" and payload.role == "owner":
        raise HTTPException(403, "Admins cannot grant owner role")
    try:
        row = await add_member(db, organization_id=organization_id, email=str(payload.email), role=payload.role)
        await write_audit(db, request, principal, action="organization.member_add", resource_type="membership", resource_id=str(row.id), metadata={"role": payload.role})
        await db.commit()
        return {"id": str(row.id), "user_id": str(row.user_id), "role": row.role, "active": row.active}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api-keys")
async def create_api_key(payload: ApiKeyCreateRequest, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    if principal.organization_id is None:
        raise HTTPException(400, "API keys require an authenticated organization")
    row, raw = await create_key(db, organization_id=principal.organization_id, user_id=principal.user_id, name=payload.name, scopes=payload.scopes, expires_in_days=payload.expires_in_days)
    await write_audit(db, request, principal, action="api_key.create", resource_type="api_key", resource_id=str(row.id), metadata={"scopes": row.scopes})
    await db.commit()
    return {"id": str(row.id), "name": row.name, "prefix": row.prefix, "scopes": row.scopes, "expires_at": row.expires_at, "api_key": raw}


@router.get("/api-keys")
async def list_api_keys(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    rows = await db.execute(select(ApiKey).where(ApiKey.organization_id == principal.organization_id).order_by(ApiKey.created_at.desc()))
    return {"api_keys": [{"id": str(row.id), "name": row.name, "prefix": row.prefix, "scopes": row.scopes, "expires_at": row.expires_at, "last_used_at": row.last_used_at, "revoked_at": row.revoked_at} for row in rows.scalars().all()]}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: UUID, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    row = await db.get(ApiKey, key_id)
    if not row or row.organization_id != principal.organization_id:
        raise HTTPException(404, "API key not found")
    row.revoked_at = datetime.utcnow()
    await write_audit(db, request, principal, action="api_key.revoke", resource_type="api_key", resource_id=str(row.id))
    await db.commit()
    return {"ok": True}


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(request: Request, response: Response, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.user_id is None:
        return {"revoked": 0}
    result = await db.execute(update(AuthSession).where(AuthSession.user_id == principal.user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=datetime.utcnow()))
    await write_audit(db, request, principal, action="auth.sessions.revoke_all", resource_type="user", resource_id=str(principal.user_id))
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    await db.commit()
    return {"revoked": result.rowcount or 0}


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: UUID, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    existing = await db.get(ApiKey, key_id)
    if not existing or existing.organization_id != principal.organization_id:
        raise HTTPException(404, "API key not found")
    existing.revoked_at = datetime.utcnow()
    row, raw = await create_key(db, organization_id=principal.organization_id, user_id=principal.user_id, name=existing.name, scopes=existing.scopes, expires_in_days=max(1, (existing.expires_at - datetime.utcnow()).days) if existing.expires_at else None)
    await write_audit(db, request, principal, action="api_key.rotate", resource_type="api_key", resource_id=str(row.id), metadata={"replaced_key_id": str(existing.id)})
    await db.commit()
    return {"id": str(row.id), "name": row.name, "prefix": row.prefix, "scopes": row.scopes, "expires_at": row.expires_at, "api_key": raw}


@router.get("/audit-log")
async def audit_log(limit: int = 100, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    rows = await db.execute(select(AuditLog).where(AuditLog.organization_id == principal.organization_id).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 200)))
    return {"events": [{"id": row.id, "action": row.action, "resource_type": row.resource_type, "resource_id": row.resource_id, "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None, "metadata": row.metadata_json, "created_at": row.created_at} for row in rows.scalars().all()]}


@router.post("/usage/events")
async def usage_event(payload: UsageEventRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("content:write"))):
    if principal.organization_id is None:
        raise HTTPException(400, "Usage metering requires an authenticated organization")
    channel_id = UUID(payload.channel_id) if payload.channel_id else None
    project_id = UUID(payload.project_id) if payload.project_id else None
    row = await record_usage(db, organization_id=principal.organization_id, user_id=principal.user_id, service=payload.service, action=payload.action, units=payload.units, unit=payload.unit, estimated_cost_usd=payload.estimated_cost_usd, channel_id=channel_id, project_id=project_id, metadata=payload.metadata)
    await db.commit()
    return {"id": str(row.id)}


@router.get("/usage/summary")
async def usage_summary(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.organization_id is None:
        return {"organization_id": None, "current_month": {"events": 0, "units": 0, "estimated_cost_usd": 0}}
    now = datetime.utcnow()
    start = datetime(now.year, now.month, 1)
    base = select(UsageEvent).where(UsageEvent.organization_id == principal.organization_id, UsageEvent.created_at >= start)
    rows = (await db.execute(base)).scalars().all()
    return {
        "organization_id": str(principal.organization_id),
        "current_month": {
            "events": len(rows),
            "units": float(sum(row.units for row in rows)),
            "estimated_cost_usd": float(sum(row.estimated_cost_usd for row in rows)),
        },
        "by_service": {},
    }
