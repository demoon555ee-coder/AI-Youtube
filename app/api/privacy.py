from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, verify_password
from app.db.session import get_db
from app.models import PrivacyRequest, User
from app.privacy.service import build_user_export, create_deletion_request
from app.services.audit import write_audit

router = APIRouter(prefix="/api/v1/privacy", tags=["privacy"])


class DeletionRequestPayload(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    reason: str | None = Field(default=None, max_length=2000)


@router.get("/export")
async def export_my_data(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail="Data export requires an authenticated user")
    try:
        return await build_user_export(db, user_id=principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc


@router.post("/deletion-request")
async def request_deletion(
    payload: DeletionRequestPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.user_id is None or principal.auth_type != "session":
        raise HTTPException(status_code=403, detail="Account deletion requires an authenticated browser session")
    user = await db.get(User, principal.user_id)
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is required")
    row = await create_deletion_request(
        db,
        user_id=user.id,
        organization_id=principal.organization_id,
        reason=payload.reason,
    )
    await write_audit(
        db,
        request,
        principal,
        action="privacy.deletion_request.create",
        resource_type="privacy_request",
        resource_id=str(row.id),
    )
    await db.commit()
    return {"request_id": str(row.id), "request_type": row.request_type, "status": row.status}


@router.get("/requests")
async def list_my_privacy_requests(
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.user_id is None:
        return {"requests": []}
    rows = await db.execute(
        select(PrivacyRequest)
        .where(PrivacyRequest.user_id == principal.user_id)
        .order_by(PrivacyRequest.created_at.desc())
        .limit(100)
    )
    return {
        "requests": [
            {
                "id": str(row.id),
                "request_type": row.request_type,
                "status": row.status,
                "reason": row.reason,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in rows.scalars().all()
        ]
    }


@router.post("/requests/{request_id}/cancel")
async def cancel_privacy_request(
    request_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    if principal.user_id is None:
        raise HTTPException(status_code=403, detail="Authenticated user required")
    row = await db.get(PrivacyRequest, request_id, with_for_update=True)
    if not row or row.user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    if row.status != "REQUESTED":
        raise HTTPException(status_code=409, detail="Privacy request can no longer be cancelled")
    row.status = "CANCELLED"
    await write_audit(db, request, principal, action="privacy.request.cancel", resource_type="privacy_request", resource_id=str(row.id))
    await db.commit()
    return {"request_id": str(row.id), "status": row.status}
