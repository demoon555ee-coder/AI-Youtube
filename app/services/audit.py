from __future__ import annotations

from typing import Any
import re

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal
from app.models.auth import AuditLog

SENSITIVE_KEYS = {
    "password", "password_hash", "token", "access_token", "refresh_token",
    "authorization", "cookie", "set-cookie", "api_key", "secret", "client_secret",
    "private_key", "encryption_key", "session_token", "csrf_token",
}


def _normalize_key(key: Any) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key))
    return text.lower().replace("-", "_")


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _normalize_key(key) in SENSITIVE_KEYS else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


async def write_audit(
    db: AsyncSession,
    request: Request,
    principal: Principal,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> AuditLog | None:
    if principal.organization_id is None:
        return None
    row = AuditLog(
        organization_id=principal.organization_id,
        actor_user_id=principal.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500],
        metadata_json=redact_sensitive(metadata or {}),
    )
    db.add(row)
    return row
