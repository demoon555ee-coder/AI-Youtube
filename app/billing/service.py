from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.providers import WebhookEnvelope, provider_from_settings
from app.config import settings
from app.models.auth import UsageEvent
from app.models.workflow import WorkflowRun
from app.models.domain import VideoProject
from app.models.channel import Channel
from app.models.billing import (
    BillingAccount,
    BillingCheckoutSession,
    BillingInvoice,
    BillingMeterEvent,
    BillingPlan,
    BillingSubscription,
    BillingUsageCounter,
    BillingWebhookEvent,
)

DEFAULT_PLANS = [
    {"code": "free", "name": "Free", "description": "Starter workspace", "monthly_price_cents": 0,
     "entitlements": {"max_channels": 1, "monthly_video_minutes": 10, "monthly_llm_requests": 200, "monthly_render_minutes": 30, "monthly_storage_gb": 2, "monthly_video_projects": 10, "autopilot_enabled": False, "full_auto_publish": False}},
    {"code": "creator", "name": "Creator", "description": "For one active creator", "monthly_price_cents": 4900,
     "entitlements": {"max_channels": 3, "monthly_video_minutes": 60, "monthly_llm_requests": 2000, "monthly_render_minutes": 240, "monthly_storage_gb": 25, "monthly_video_projects": 50, "autopilot_enabled": True, "full_auto_publish": False}},
    {"code": "pro", "name": "Pro", "description": "For growing content teams", "monthly_price_cents": 14900,
     "entitlements": {"max_channels": 10, "monthly_video_minutes": 240, "monthly_llm_requests": 10000, "monthly_render_minutes": 1000, "monthly_storage_gb": 100, "monthly_video_projects": 250, "autopilot_enabled": True, "full_auto_publish": True}},
    {"code": "studio", "name": "Studio", "description": "For multi-channel operations", "monthly_price_cents": 39900,
     "entitlements": {"max_channels": 50, "monthly_video_minutes": 1000, "monthly_llm_requests": 50000, "monthly_render_minutes": 5000, "monthly_storage_gb": 500, "monthly_video_projects": 1000, "autopilot_enabled": True, "full_auto_publish": True}},
]

METRIC_ALIASES = {
    "llm": "monthly_llm_requests",
    "tts": "monthly_video_minutes",
    "video_generation": "monthly_video_minutes",
    "render": "monthly_render_minutes",
    "storage": "monthly_storage_gb",
    "workflow": "monthly_video_projects",
}

ACCESSIBLE_SUBSCRIPTION_STATUSES = {"ACTIVE", "TRIALING", "PAST_DUE"}


class BillingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def seed_plans(self) -> list[BillingPlan]:
        existing = {row.code: row for row in (await self.db.execute(select(BillingPlan))).scalars().all()}
        rows = []
        price_map = {
            "creator": settings.stripe_price_creator,
            "pro": settings.stripe_price_pro,
            "studio": settings.stripe_price_studio,
        }
        for item in DEFAULT_PLANS:
            row = existing.get(item["code"])
            if not row:
                row = BillingPlan(**item)
                self.db.add(row)
            else:
                row.name = item["name"]
                row.description = item["description"]
                row.monthly_price_cents = item["monthly_price_cents"]
                row.entitlements = item["entitlements"]
                row.active = True
            row.provider_price_reference = price_map.get(item["code"]) or None
            rows.append(row)
        await self.db.flush()
        return rows

    async def ensure_account(self, organization_id: UUID) -> BillingAccount:
        row = await self.db.scalar(select(BillingAccount).where(BillingAccount.organization_id == organization_id).with_for_update())
        if row:
            return row
        row = BillingAccount(organization_id=organization_id, provider=settings.billing_provider, currency=settings.billing_currency)
        self.db.add(row)
        await self.db.flush()
        return row

    async def current_subscription(self, organization_id: UUID) -> tuple[BillingSubscription, BillingPlan]:
        await self.seed_plans()
        q = await self.db.execute(
            select(BillingSubscription, BillingPlan)
            .join(BillingPlan, BillingPlan.id == BillingSubscription.plan_id)
            .where(BillingSubscription.organization_id == organization_id, BillingSubscription.status.in_(ACCESSIBLE_SUBSCRIPTION_STATUSES))
            .order_by(BillingSubscription.current_period_end.desc())
            .limit(1)
        )
        found = q.first()
        now = datetime.utcnow()
        if found:
            sub, plan = found
            if sub.cancel_at_period_end and sub.current_period_end <= now:
                sub.status = "CANCELLED"
            else:
                return sub, plan
        period_start = _month_start(now)
        end = _next_month(period_start)
        plan = await self.db.scalar(select(BillingPlan).where(BillingPlan.code == "free"))
        sub = BillingSubscription(id=uuid4(), organization_id=organization_id, plan_id=plan.id, status="ACTIVE", current_period_start=period_start, current_period_end=end)
        return sub, plan

    async def catalog(self) -> list[BillingPlan]:
        await self.seed_plans()
        return list((await self.db.execute(select(BillingPlan).where(BillingPlan.active.is_(True)).order_by(BillingPlan.monthly_price_cents.asc()))).scalars().all())

    async def start_checkout(self, organization_id: UUID, plan_code: str) -> dict:
        plan = await self.db.scalar(select(BillingPlan).where(BillingPlan.code == plan_code, BillingPlan.active.is_(True)))
        if not plan:
            raise ValueError("Billing plan not found")
        if plan.code == "free":
            raise ValueError("Free plan does not require checkout")
        account = await self.ensure_account(organization_id)
        if account.provider != settings.billing_provider and not account.customer_reference:
            account.provider = settings.billing_provider
        if account.provider == "stripe" and account.customer_reference and not account.customer_reference.startswith("cus_"):
            account.customer_reference = None
        provider = provider_from_settings(account.provider)
        customer_reference = account.customer_reference
        if provider.name == "mock" and not customer_reference:
            customer_reference = f"cust_{uuid4().hex}"
            account.customer_reference = customer_reference
        checkout = await provider.create_checkout(
            customer_reference=customer_reference,
            organization_reference=str(organization_id),
            plan_code=plan.code,
            return_url=settings.billing_return_url,
        )
        self.db.add(BillingCheckoutSession(
            organization_id=organization_id,
            provider=checkout.provider,
            external_checkout_reference=checkout.id,
            plan_code=plan.code,
            status="OPEN",
            url=checkout.url,
            metadata_json={"organization_id": str(organization_id)},
        ))
        await self.db.flush()
        return {"checkout_id": checkout.id, "url": checkout.url, "provider": checkout.provider, "plan": plan.code}

    async def activate_plan(self, organization_id: UUID, plan_code: str, *, provider_subscription_reference: str | None = None) -> BillingSubscription:
        plan = await self.db.scalar(select(BillingPlan).where(BillingPlan.code == plan_code, BillingPlan.active.is_(True)))
        if not plan:
            raise ValueError("Billing plan not found")
        return await self.upsert_provider_subscription(
            organization_id,
            plan_code,
            provider_subscription_reference=provider_subscription_reference,
            status="ACTIVE",
        )

    async def upsert_provider_subscription(
        self,
        organization_id: UUID,
        plan_code: str,
        *,
        provider_subscription_reference: str | None,
        status: str,
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool = False,
        metadata: dict | None = None,
    ) -> BillingSubscription:
        plan = await self.db.scalar(select(BillingPlan).where(BillingPlan.code == plan_code, BillingPlan.active.is_(True)))
        if not plan:
            raise ValueError("Billing plan not found")
        q = await self.db.execute(
            select(BillingSubscription).where(
                BillingSubscription.organization_id == organization_id,
                or_(
                    BillingSubscription.provider_subscription_reference == provider_subscription_reference,
                    BillingSubscription.status.in_(ACCESSIBLE_SUBSCRIPTION_STATUSES),
                ),
            ).with_for_update()
        )
        rows = list(q.scalars().all())
        target = None
        if provider_subscription_reference:
            target = next((item for item in rows if item.provider_subscription_reference == provider_subscription_reference), None)
        now = datetime.utcnow()
        start = current_period_start or _month_start(now)
        end = current_period_end or _next_month(start)
        normalized_status = str(status or "ACTIVE").upper()
        if normalized_status == "CANCELED":
            normalized_status = "CANCELLED"
        if target is not None and target.status == "CANCELLED" and normalized_status in ACCESSIBLE_SUBSCRIPTION_STATUSES:
            return target
        if target is None:
            for existing in rows:
                if existing.provider_subscription_reference != provider_subscription_reference and existing.status in ACCESSIBLE_SUBSCRIPTION_STATUSES:
                    existing.status = "SUPERSEDED"
            target = BillingSubscription(
                organization_id=organization_id,
                plan_id=plan.id,
                provider_subscription_reference=provider_subscription_reference,
                status=normalized_status,
                current_period_start=start,
                current_period_end=end,
                cancel_at_period_end=cancel_at_period_end,
                metadata_json=metadata or {},
            )
            self.db.add(target)
        else:
            target.plan_id = plan.id
            target.status = normalized_status
            target.current_period_start = start
            target.current_period_end = end
            target.cancel_at_period_end = cancel_at_period_end
            target.metadata_json = metadata or target.metadata_json or {}
        await self.ensure_account(organization_id)
        await self.db.flush()
        return target

    async def cancel(self, organization_id: UUID, *, at_period_end: bool = True) -> BillingSubscription:
        sub, _ = await self.current_subscription(organization_id)
        if sub.provider_subscription_reference:
            account = await self.ensure_account(organization_id)
            await provider_from_settings(account.provider).cancel_subscription(sub.provider_subscription_reference, at_period_end=at_period_end)
        if at_period_end:
            sub.cancel_at_period_end = True
        else:
            sub.status = "CANCELLED"
            sub.cancel_at_period_end = False
        await self.db.flush()
        return sub

    async def current_usage(self, organization_id: UUID) -> dict[str, float]:
        now = datetime.utcnow()
        start = datetime(now.year, now.month, 1)
        rows = (await self.db.execute(select(BillingUsageCounter).where(BillingUsageCounter.organization_id == organization_id, BillingUsageCounter.period_start == start))).scalars().all()
        usage = {row.metric: float(row.units) for row in rows}
        scoped_runs = await self.db.scalar(
            select(func.count(WorkflowRun.id))
            .join(VideoProject, VideoProject.id == WorkflowRun.project_id)
            .join(Channel, Channel.id == VideoProject.channel_id)
            .where(WorkflowRun.created_at >= start, Channel.organization_id == organization_id)
        )
        usage["monthly_video_projects"] = float(scoped_runs or 0)
        return usage

    async def entitlement(self, organization_id: UUID, key: str) -> dict:
        sub, plan = await self.current_subscription(organization_id)
        used = (await self.current_usage(organization_id)).get(key, 0.0)
        limit = plan.entitlements.get(key)
        if isinstance(limit, bool):
            allowed = bool(limit)
        elif limit is None:
            allowed = True
        elif isinstance(limit, (int, float)) and used <= float(limit):
            allowed = True
        else:
            allowed = False
        return {"plan": plan.code, "key": key, "limit": limit, "used": used, "allowed": allowed, "period_end": sub.current_period_end}

    async def meter(self, organization_id: UUID, *, service: str, units: float, estimated_cost_usd: float = 0.0, action: str = "usage", user_id: UUID | None = None, channel_id: UUID | None = None, project_id: UUID | None = None, idempotency_key: str | None = None, metadata: dict | None = None) -> BillingUsageCounter:
        if units < 0 or estimated_cost_usd < 0:
            raise ValueError("Usage values cannot be negative")
        sub, plan = await self.current_subscription(organization_id)
        now = datetime.utcnow(); start = datetime(now.year, now.month, 1)
        metric = METRIC_ALIASES.get(service, service)
        if idempotency_key:
            insert_event = pg_insert(BillingMeterEvent).values(
                organization_id=organization_id, user_id=user_id, channel_id=channel_id, project_id=project_id,
                idempotency_key=idempotency_key, service=service, units=units, estimated_cost_usd=estimated_cost_usd, metadata_json=metadata or {},
            ).on_conflict_do_nothing(index_elements=["organization_id", "idempotency_key"]).returning(BillingMeterEvent.id)
            inserted = (await self.db.execute(insert_event)).scalar_one_or_none()
            if inserted is None:
                counter = await self.db.scalar(select(BillingUsageCounter).where(BillingUsageCounter.organization_id == organization_id, BillingUsageCounter.period_start == start, BillingUsageCounter.metric == metric).with_for_update())
                if counter:
                    return counter

        create_counter = pg_insert(BillingUsageCounter).values(
            organization_id=organization_id, period_start=start, period_end=sub.current_period_end, metric=metric, units=0.0, estimated_cost_usd=0.0
        ).on_conflict_do_nothing(index_elements=["organization_id", "period_start", "metric"])
        await self.db.execute(create_counter)
        counter = await self.db.scalar(select(BillingUsageCounter).where(BillingUsageCounter.organization_id == organization_id, BillingUsageCounter.period_start == start, BillingUsageCounter.metric == metric).with_for_update())
        if counter is None:
            raise RuntimeError("Usage counter could not be created")
        limit = plan.entitlements.get(metric)
        current = float(counter.units)
        if limit is not None and current + units > float(limit):
            raise ValueError(f"Monthly entitlement exceeded for {metric}")
        counter.units += units
        counter.estimated_cost_usd += estimated_cost_usd
        self.db.add(UsageEvent(organization_id=organization_id, user_id=user_id, channel_id=channel_id, project_id=project_id, service=service, action=action, units=units, unit="request", estimated_cost_usd=estimated_cost_usd, metadata_json={**(metadata or {}), "meter_idempotency_key": idempotency_key}))
        await self.db.flush()
        return counter

    async def summary(self, organization_id: UUID) -> dict:
        sub, plan = await self.current_subscription(organization_id)
        return {"plan": {"code": plan.code, "name": plan.name, "monthly_price_cents": plan.monthly_price_cents, "currency": plan.currency}, "period": {"start": sub.current_period_start, "end": sub.current_period_end}, "usage": await self.current_usage(organization_id), "entitlements": plan.entitlements}

    async def invoice_preview(self, organization_id: UUID) -> dict:
        sub, plan = await self.current_subscription(organization_id)
        return {"currency": plan.currency, "plan_amount_cents": plan.monthly_price_cents, "usage": await self.current_usage(organization_id), "estimated_total_cents": plan.monthly_price_cents, "period_start": sub.current_period_start, "period_end": sub.current_period_end}

    async def receive_webhook(self, body: bytes, signature: str | None) -> dict:
        provider = provider_from_settings(settings.billing_provider)
        envelope = provider.verify_webhook(body, signature, settings.billing_webhook_secret)
        stmt = pg_insert(BillingWebhookEvent).values(
            provider=provider.name,
            external_event_reference=envelope.event_id,
            event_type=envelope.event_type,
            payload=envelope.payload,
            status="RECEIVED",
        ).on_conflict_do_nothing(index_elements=["provider", "external_event_reference"])
        result = await self.db.execute(stmt)
        await self.db.flush()
        if result.rowcount == 0:
            existing = await self.db.scalar(select(BillingWebhookEvent).where(
                BillingWebhookEvent.provider == provider.name,
                BillingWebhookEvent.external_event_reference == envelope.event_id,
            ))
            return {"ok": True, "duplicate": True, "event_id": envelope.event_id, "status": existing.status if existing else "RECEIVED"}
        return {"ok": True, "duplicate": False, "event_id": envelope.event_id, "event_type": envelope.event_type, "status": "RECEIVED"}

    async def process_webhook(self, body: bytes, signature: str | None) -> dict:
        result = await self.receive_webhook(body, signature)
        if result.get("duplicate"):
            return result
        event = await self.db.scalar(select(BillingWebhookEvent).where(BillingWebhookEvent.external_event_reference == result["event_id"]))
        if event:
            await self.process_webhook_event(event.id)
            return {"ok": True, "duplicate": False, "event_id": event.external_event_reference, "event_type": event.event_type}
        return result

    async def process_webhook_event(self, event_id: UUID) -> None:
        event = await self.db.get(BillingWebhookEvent, event_id, with_for_update=True)
        if not event:
            raise ValueError("Billing webhook event not found")
        if event.status == "PROCESSED":
            return
        event.status = "PROCESSING"
        event.attempts = int(event.attempts or 0) + 1
        event.next_attempt_at = None
        event.error_message = None
        await self.db.flush()
        await self._apply_provider_event(event.provider, event.event_type, event.payload)
        event.status = "PROCESSED"
        event.processed_at = datetime.utcnow()
        event.error_message = None
        await self.db.flush()

    async def process_pending_webhooks(self, limit: int = 5) -> int:
        processed = 0
        for _ in range(limit):
            now = datetime.utcnow()
            q = await self.db.execute(
                select(BillingWebhookEvent)
                .where(
                    BillingWebhookEvent.status.in_({"RECEIVED", "RETRY"}),
                    (BillingWebhookEvent.next_attempt_at.is_(None) | (BillingWebhookEvent.next_attempt_at <= now)),
                )
                .order_by(BillingWebhookEvent.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            event = q.scalar_one_or_none()
            if not event:
                break
            try:
                await self.process_webhook_event(event.id)
                await self.db.commit()
                processed += 1
            except Exception as exc:
                await self.db.rollback()
                retry_event = await self.db.get(BillingWebhookEvent, event.id, with_for_update=True)
                if retry_event:
                    attempts = int(retry_event.attempts or 0)
                    retry_event.error_message = str(exc)[:1000]
                    if attempts < 5:
                        retry_event.status = "RETRY"
                        retry_event.next_attempt_at = datetime.utcnow() + timedelta(seconds=min(300, 2 ** max(attempts - 1, 0)))
                    else:
                        retry_event.status = "FAILED"
                        retry_event.next_attempt_at = None
                    await self.db.commit()
        return processed

    async def _apply_provider_event(self, provider_name: str, event_type: str, payload: dict) -> None:
        if provider_name != "stripe":
            await self._apply_legacy_event(event_type, payload)
            return
        obj = ((payload.get("data") or {}).get("object") or {})
        if not isinstance(obj, dict):
            return
        organization_id = await self._resolve_organization(obj, event_type)
        if event_type == "checkout.session.completed":
            session_id = str(obj.get("id") or "")
            if session_id:
                checkout = await self.db.scalar(select(BillingCheckoutSession).where(BillingCheckoutSession.provider == "stripe", BillingCheckoutSession.external_checkout_reference == session_id).with_for_update())
                if checkout:
                    checkout.status = "COMPLETED"
                    checkout.completed_at = datetime.utcnow()
                    organization_id = checkout.organization_id
            customer = obj.get("customer")
            if organization_id:
                account = await self.ensure_account(organization_id)
                if customer:
                    account.customer_reference = str(customer)
                subscription_ref = obj.get("subscription")
                plan_code = str((obj.get("metadata") or {}).get("plan_code") or "")
                if subscription_ref and plan_code:
                    await self.upsert_provider_subscription(organization_id, plan_code, provider_subscription_reference=str(subscription_ref), status="ACTIVE")
            return

        if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
            if not organization_id:
                return
            plan_code = self._plan_code_from_subscription(obj)
            if not plan_code:
                raise ValueError("Stripe subscription event has no mapped plan")
            status = str(obj.get("status") or "").upper()
            if status == "CANCELED":
                status = "CANCELLED"
            start = _epoch_datetime(obj.get("current_period_start"))
            end = _epoch_datetime(obj.get("current_period_end"))
            cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
            sub = await self.upsert_provider_subscription(
                organization_id,
                plan_code,
                provider_subscription_reference=str(obj.get("id")) if obj.get("id") else None,
                status=status,
                current_period_start=start,
                current_period_end=end,
                cancel_at_period_end=cancel_at_period_end,
                metadata={**(obj.get("metadata") or {}), "provider_status": obj.get("status"), "provider_customer": obj.get("customer")},
            )
            if obj.get("customer"):
                account = await self.ensure_account(organization_id)
                account.customer_reference = str(obj.get("customer"))
                await self.db.flush()
            return

        if event_type == "customer.subscription.deleted":
            if not organization_id:
                return
            ref = str(obj.get("id") or "")
            if ref:
                sub = await self.db.scalar(select(BillingSubscription).where(BillingSubscription.provider_subscription_reference == ref).with_for_update())
                if sub:
                    sub.status = "CANCELLED"
                    sub.cancel_at_period_end = False
            return

        if event_type in {"invoice.paid", "invoice.payment_failed"}:
            if not organization_id:
                return
            await self._upsert_invoice(organization_id, obj, "PAID" if event_type == "invoice.paid" else "PAYMENT_FAILED")
            if event_type == "invoice.payment_failed":
                subscription_ref = str(obj.get("subscription") or "")
                if subscription_ref:
                    sub = await self.db.scalar(select(BillingSubscription).where(BillingSubscription.provider_subscription_reference == subscription_ref).with_for_update())
                    if sub and sub.status == "ACTIVE":
                        sub.status = "PAST_DUE"
            return

    async def _resolve_organization(self, obj: dict, event_type: str) -> UUID | None:
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        raw = metadata.get("organization_id") or obj.get("client_reference_id")
        if raw:
            try:
                return UUID(str(raw))
            except ValueError as exc:
                raise ValueError("Stripe event contains invalid organization_id") from exc
        customer = obj.get("customer")
        if customer:
            account = await self.db.scalar(select(BillingAccount).where(BillingAccount.customer_reference == str(customer)))
            if account:
                return account.organization_id
        subscription_ref = obj.get("subscription")
        if event_type.startswith("invoice.") and subscription_ref:
            sub = await self.db.scalar(select(BillingSubscription).where(BillingSubscription.provider_subscription_reference == str(subscription_ref)))
            if sub:
                return sub.organization_id
        return None

    def _plan_code_from_subscription(self, obj: dict) -> str:
        metadata = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        if metadata.get("plan_code"):
            return str(metadata["plan_code"])
        items = obj.get("items") if isinstance(obj.get("items"), dict) else {}
        data = items.get("data") if isinstance(items.get("data"), list) else []
        price_id = None
        if data and isinstance(data[0], dict):
            price = data[0].get("price") if isinstance(data[0].get("price"), dict) else {}
            price_id = price.get("id")
        if not price_id:
            return ""
        return {value: key for key, value in {
            "creator": settings.stripe_price_creator,
            "pro": settings.stripe_price_pro,
            "studio": settings.stripe_price_studio,
        }.items() if value}.get(str(price_id), "")

    async def _upsert_invoice(self, organization_id: UUID, obj: dict, status: str) -> BillingInvoice:
        ref = str(obj.get("id") or "")
        invoice = await self.db.scalar(select(BillingInvoice).where(BillingInvoice.provider_invoice_reference == ref).with_for_update()) if ref else None
        start = _epoch_datetime(obj.get("period_start")) or _month_start(datetime.utcnow())
        end = _epoch_datetime(obj.get("period_end")) or _next_month(start)
        paid_at = _epoch_datetime(((obj.get("status_transitions") or {}).get("paid_at")))
        if invoice is None:
            invoice = BillingInvoice(
                organization_id=organization_id,
                provider_invoice_reference=ref or None,
                status=status,
                currency=str(obj.get("currency") or settings.billing_currency).upper(),
                subtotal_cents=int(obj.get("subtotal") or 0),
                total_cents=int(obj.get("total") or 0),
                period_start=start,
                period_end=end,
                hosted_invoice_url=obj.get("hosted_invoice_url"),
                paid_at=paid_at if status == "PAID" else None,
            )
            self.db.add(invoice)
        else:
            invoice.organization_id = organization_id
            invoice.status = status
            invoice.subtotal_cents = int(obj.get("subtotal") or invoice.subtotal_cents)
            invoice.total_cents = int(obj.get("total") or invoice.total_cents)
            invoice.period_start = start
            invoice.period_end = end
            invoice.hosted_invoice_url = obj.get("hosted_invoice_url") or invoice.hosted_invoice_url
            invoice.paid_at = paid_at if status == "PAID" else invoice.paid_at
        await self.db.flush()
        return invoice

    async def _apply_legacy_event(self, event_type: str, payload: dict) -> None:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return
        organization_id = data.get("organization_id")
        if not organization_id:
            return
        try:
            org_id = UUID(str(organization_id))
        except ValueError as exc:
            raise ValueError("Webhook contains invalid organization_id") from exc
        if event_type in {"subscription.activated", "subscription.updated"}:
            plan_code = str(data.get("plan_code") or "")
            if plan_code:
                await self.activate_plan(org_id, plan_code, provider_subscription_reference=data.get("subscription_reference"))
        elif event_type == "subscription.cancelled":
            sub, _ = await self.current_subscription(org_id)
            sub.status = "CANCELLED"
            sub.cancel_at_period_end = False


def _epoch_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.utcfromtimestamp(int(value))
    except (TypeError, ValueError, OSError):
        return None


def _month_start(value: datetime) -> datetime:
    return datetime(value.year, value.month, 1)


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1)
    return datetime(value.year, value.month + 1, 1)
