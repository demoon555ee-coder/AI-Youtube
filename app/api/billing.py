from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import Principal, get_current_principal, permission_dependency
from app.billing.service import BillingService
from app.db.session import get_db
from app.config import settings
from app.models.billing import BillingPlan, BillingSubscription
from app.schemas.billing import ActivatePlanRequest, CancelSubscriptionRequest, CheckoutRequest, MeterRequest
from app.services.audit import write_audit

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _plan(row: BillingPlan) -> dict:
    return {"id": str(row.id), "code": row.code, "name": row.name, "description": row.description, "monthly_price_cents": row.monthly_price_cents, "currency": row.currency, "entitlements": row.entitlements, "active": row.active}


def _subscription(row: BillingSubscription, plan: BillingPlan | None = None) -> dict:
    return {"id": str(row.id), "plan_code": plan.code if plan else None, "status": row.status, "current_period_start": row.current_period_start, "current_period_end": row.current_period_end, "cancel_at_period_end": row.cancel_at_period_end, "provider_subscription_reference": bool(row.provider_subscription_reference)}


@router.get("/catalog")
async def catalog(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    plans = await BillingService(db).catalog()
    return {"plans": [_plan(row) for row in plans]}


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.organization_id is None:
        return {"plan": {"code": "dev", "name": "Local Development", "monthly_price_cents": 0, "currency": "USD"}, "usage": {}, "entitlements": {}}
    return await BillingService(db).summary(principal.organization_id)


@router.get("/invoice-preview")
async def invoice_preview(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.organization_id is None:
        raise HTTPException(400, "Billing requires an authenticated organization")
    return await BillingService(db).invoice_preview(principal.organization_id)


@router.get("/entitlements/{key}")
async def entitlement(key: str, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_current_principal)):
    if principal.organization_id is None:
        return {"plan": "dev", "key": key, "limit": None, "used": 0, "allowed": True}
    return await BillingService(db).entitlement(principal.organization_id, key)


@router.post("/checkout")
async def checkout(payload: CheckoutRequest, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    if principal.organization_id is None:
        raise HTTPException(400, "Billing requires an authenticated organization")
    try:
        result = await BillingService(db).start_checkout(principal.organization_id, payload.plan_code)
        await write_audit(db, request, principal, action="billing.checkout.create", resource_type="billing_plan", resource_id=payload.plan_code)
        await db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/dev/activate")
async def activate(payload: ActivatePlanRequest, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    if settings.app_env == "production":
        raise HTTPException(404, "Not found")
    if principal.organization_id is None:
        raise HTTPException(400, "Billing requires an authenticated organization")
    try:
        row = await BillingService(db).activate_plan(principal.organization_id, payload.plan_code, provider_subscription_reference=payload.provider_subscription_reference)
        await write_audit(db, request, principal, action="billing.subscription.activate", resource_type="subscription", resource_id=str(row.id), metadata={"plan_code": payload.plan_code})
        await db.commit()
        return {"subscription_id": str(row.id), "status": row.status, "plan_code": payload.plan_code}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/cancel")
async def cancel(payload: CancelSubscriptionRequest, request: Request, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("admin:manage"))):
    if principal.organization_id is None:
        raise HTTPException(400, "Billing requires an authenticated organization")
    try:
        row = await BillingService(db).cancel(principal.organization_id, at_period_end=payload.at_period_end)
        await write_audit(db, request, principal, action="billing.subscription.cancel", resource_type="subscription", resource_id=str(row.id), metadata={"at_period_end": payload.at_period_end})
        await db.commit()
        return {"subscription_id": str(row.id), "status": row.status, "cancel_at_period_end": row.cancel_at_period_end}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/meter")
async def meter(payload: MeterRequest, db: AsyncSession = Depends(get_db), principal: Principal = Depends(permission_dependency("content:write"))):
    if principal.organization_id is None:
        return {"metered": False, "reason": "dev-fallback"}
    try:
        row = await BillingService(db).meter(
            principal.organization_id,
            service=payload.service,
            units=payload.units,
            estimated_cost_usd=payload.estimated_cost_usd,
            action=payload.action,
            user_id=principal.user_id,
            channel_id=UUID(payload.channel_id) if payload.channel_id else None,
            project_id=UUID(payload.project_id) if payload.project_id else None,
            idempotency_key=payload.idempotency_key,
            metadata=payload.metadata,
        )
        await db.commit()
        return {"metered": True, "metric": row.metric, "units": row.units, "estimated_cost_usd": row.estimated_cost_usd}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(402, str(exc)) from exc


@router.post("/webhooks", include_in_schema=False, status_code=202)
async def billing_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("Stripe-Signature") or request.headers.get("X-Billing-Signature")
    try:
        # Webhooks are persisted first and processed asynchronously by the durable worker.
        result = await BillingService(db).receive_webhook(body, signature)
        await db.commit()
        return {**result, "queued": True}
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(400, str(exc)) from exc
