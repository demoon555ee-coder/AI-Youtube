from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_session, hash_password, issue_api_key, verify_password
from app.models.auth import ApiKey, Membership, Organization, User, UsageEvent


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:110] or f"studio-{secrets.token_hex(4)}"


async def unique_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug = base
    for i in range(1, 100):
        exists = await db.scalar(select(Organization.id).where(Organization.slug == slug))
        if not exists:
            return slug
        slug = f"{base[:100]}-{i}"
    return f"{base[:90]}-{secrets.token_hex(5)}"


async def register(db: AsyncSession, *, email: str, password: str, name: str, organization_name: str):
    email_norm = email.strip().lower()
    existing = await db.scalar(select(User).where(User.email == email_norm))
    if existing:
        raise ValueError("Unable to create account")
    user = User(email=email_norm, password_hash=hash_password(password), name=name.strip())
    org = Organization(name=organization_name.strip(), slug=await unique_slug(db, organization_name))
    db.add_all([user, org])
    await db.flush()
    membership = Membership(user_id=user.id, organization_id=org.id, role="owner", active=True)
    db.add(membership)
    session, raw_token, csrf_token = await create_session(db, user.id)
    return user, org, membership, session, raw_token, csrf_token


async def login(db: AsyncSession, *, email: str, password: str, organization_id: str | None = None):
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not verify_password(password, user.password_hash) or not user.is_active:
        raise ValueError("Invalid email or password")
    if organization_id:
        try:
            org_uuid = UUID(organization_id)
        except ValueError as exc:
            raise ValueError("Invalid organization id") from exc
        membership = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.organization_id == org_uuid, Membership.active.is_(True)))
    else:
        membership = await db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.active.is_(True)).order_by(Membership.created_at.asc()))
    if not membership:
        raise ValueError("User has no active organization")
    session, raw_token, csrf_token = await create_session(db, user.id)
    return user, membership, session, raw_token, csrf_token


async def add_member(db: AsyncSession, *, organization_id: UUID, email: str, role: str) -> Membership:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user:
        raise ValueError("User with this email does not exist")
    existing = await db.scalar(select(Membership).where(Membership.organization_id == organization_id, Membership.user_id == user.id))
    if existing:
        existing.role = role
        existing.active = True
        await db.flush()
        return existing
    row = Membership(organization_id=organization_id, user_id=user.id, role=role, active=True)
    db.add(row)
    await db.flush()
    return row


async def create_key(db: AsyncSession, *, organization_id: UUID, user_id: UUID, name: str, scopes: list[str], expires_in_days: int | None):
    raw, digest, prefix = issue_api_key()
    row = ApiKey(
        organization_id=organization_id,
        created_by_user_id=user_id,
        name=name,
        prefix=prefix,
        key_hash=digest,
        scopes=sorted(set(scopes or ["read"])),
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days if expires_in_days else 365),
    )
    db.add(row)
    await db.flush()
    return row, raw


async def record_usage(db: AsyncSession, *, organization_id: UUID, user_id: UUID | None, service: str, action: str, units: float, unit: str, estimated_cost_usd: float, channel_id=None, project_id=None, metadata=None):
    row = UsageEvent(
        organization_id=organization_id,
        user_id=user_id,
        channel_id=channel_id,
        project_id=project_id,
        service=service,
        action=action,
        units=units,
        unit=unit,
        estimated_cost_usd=estimated_cost_usd,
        metadata_json=metadata or {},
    )
    db.add(row)
    await db.flush()
    return row
