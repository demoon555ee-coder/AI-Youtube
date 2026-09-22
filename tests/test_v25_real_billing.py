import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import re
import time

import httpx
import pytest

from app.billing.providers import StripeBillingProvider


def stripe_signature(body: bytes, secret: str, timestamp: int) -> str:
    signed = f"{timestamp}.{body.decode()}".encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_stripe_webhook_signature_requires_timestamp_and_tolerance():
    body = json.dumps({"id": "evt_123", "type": "invoice.paid", "data": {"object": {}}}).encode()
    secret = "whsec_test"
    provider = StripeBillingProvider(webhook_tolerance_seconds=300)
    now = int(time.time())
    envelope = provider.verify_webhook(body, stripe_signature(body, secret, now), secret)
    assert envelope.event_id == "evt_123"
    with pytest.raises(ValueError, match="Expired"):
        provider.verify_webhook(body, stripe_signature(body, secret, now - 1000), secret)


def test_stripe_webhook_signature_supports_secret_rotation(monkeypatch):
    body = b'{"id":"evt_rotate","type":"customer.subscription.updated","data":{"object":{}}}'
    old = "whsec_old"
    new = "whsec_new"
    monkeypatch.setattr("app.billing.providers.settings.billing_webhook_secrets", f"{new},{old}")
    provider = StripeBillingProvider(webhook_tolerance_seconds=300)
    now = int(time.time())
    envelope = provider.verify_webhook(body, stripe_signature(body, old, now), "")
    assert envelope.event_id == "evt_rotate"


def test_stripe_checkout_payload_and_cancel_are_api_compatible():
    calls = []

    async def fake_request(method, path, *, data=None):
        calls.append((method, path, dict(data or [])))
        if path == "/v1/checkout/sessions":
            return {"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/cs_test_123"}
        return {"id": "sub_test_123", "status": "active"}

    provider = StripeBillingProvider(
        secret_key="sk_test_x",
        price_map={"creator": "price_creator"},
    )
    provider._request = fake_request
    async def run():
        checkout = await provider.create_checkout(
            customer_reference=None,
            organization_reference="org-uuid",
            plan_code="creator",
            return_url="https://app.example.com/billing",
        )
        await provider.cancel_subscription("sub_test_123", at_period_end=True)
        await provider.cancel_subscription("sub_test_123", at_period_end=False)
        return checkout
    checkout = asyncio.run(run())
    assert checkout.id == "cs_test_123"
    assert calls[0][0:2] == ("POST", "/v1/checkout/sessions")
    assert calls[0][2]["mode"] == "subscription"
    assert calls[0][2]["line_items[0][price]"] == "price_creator"
    assert calls[0][2]["subscription_data[metadata][organization_id]"] == "org-uuid"
    assert calls[1][0:2] == ("POST", "/v1/subscriptions/sub_test_123")
    assert calls[1][2]["cancel_at_period_end"] == "true"
    assert calls[2][0:2] == ("DELETE", "/v1/subscriptions/sub_test_123")


def test_billing_webhook_route_uses_stripe_signature_header_and_queues_event():
    text = Path("app/api/billing.py").read_text()
    assert 'request.headers.get("Stripe-Signature")' in text
    assert '"queued": True' in text
    assert "receive_webhook" in text


def test_billing_migration_014_adds_provider_prices_and_checkout_sessions():
    text = Path("app/db/migrations.py").read_text()
    assert "014_v25_real_billing_provider" in text
    assert "provider_price_reference" in text
    assert "billing_checkout_sessions" in text
    versions = re.findall(r'"(0\d+_v[^"\n]+)"', text)
    idx = versions.index("014_v25_real_billing_provider")
    assert versions[idx].startswith("014_v25_real_billing_provider")
    assert idx < versions.index("015_v25_webhook_reliability")


def test_production_requires_stripe_credentials_and_prices(monkeypatch):
    from app.deployment import validate_production_settings
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "billing_provider", "stripe")
    monkeypatch.setattr(settings, "billing_webhook_secret", "whsec_x")
    monkeypatch.setattr(settings, "billing_webhook_secrets", "")
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    monkeypatch.setattr(settings, "stripe_price_creator", "")
    monkeypatch.setattr(settings, "stripe_price_pro", "")
    monkeypatch.setattr(settings, "stripe_price_studio", "")
    issues = {item.code for item in validate_production_settings()}
    assert {"missing_stripe_secret_key", "missing_stripe_price_creator", "missing_stripe_price_pro", "missing_stripe_price_studio"} <= issues


def test_webhook_processing_is_async_and_retryable():
    service = Path("app/billing/service.py").read_text()
    model = Path("app/models/billing.py").read_text()
    assert "process_pending_webhooks" in service
    assert 'status.in_({"RECEIVED", "RETRY"})' in service
    assert "attempts" in model
    assert "next_attempt_at" in model


def test_stripe_sandbox_check_is_read_only_and_test_key_only():
    text = Path("scripts/stripe_sandbox_check.py").read_text()
    assert 'startswith("sk_test_")' in text
    assert '.get(f"{base}/v1/prices/{price_id}")' in text
    assert 'checkout/sessions' not in text


def test_frontend_free_plan_uses_downgrade_flow_not_checkout():
    text = Path("frontend/app/billing/page.tsx").read_text()
    assert 'code==="free"' in text
    assert '"/api/v1/billing/cancel"' in text
    assert '"/api/v1/billing/checkout"' in text
