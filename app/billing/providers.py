from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str
    provider: str


@dataclass(frozen=True)
class WebhookEnvelope:
    event_id: str
    event_type: str
    payload: dict


class BillingProvider:
    name = "base"

    async def create_checkout(
        self,
        *,
        customer_reference: str | None,
        organization_reference: str,
        plan_code: str,
        return_url: str,
    ) -> CheckoutSession:
        raise NotImplementedError

    async def cancel_subscription(self, provider_subscription_reference: str, *, at_period_end: bool) -> None:
        raise NotImplementedError

    def verify_webhook(self, body: bytes, signature: str | None, secret: str) -> WebhookEnvelope:
        raise NotImplementedError

    def price_reference(self, plan_code: str) -> str | None:
        return None


class MockBillingProvider(BillingProvider):
    name = "mock"

    async def create_checkout(
        self,
        *,
        customer_reference: str | None,
        organization_reference: str,
        plan_code: str,
        return_url: str,
    ) -> CheckoutSession:
        token = secrets.token_urlsafe(18)
        return CheckoutSession(
            id=f"mock_checkout_{token}",
            url=f"{return_url}?provider=mock&checkout={token}&plan={plan_code}",
            provider=self.name,
        )

    async def cancel_subscription(self, provider_subscription_reference: str, *, at_period_end: bool) -> None:
        return None

    def verify_webhook(self, body: bytes, signature: str | None, secret: str) -> WebhookEnvelope:
        if secret:
            if not signature:
                raise ValueError("Missing webhook signature")
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature):
                raise ValueError("Invalid webhook signature")
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Invalid webhook payload") from exc
        event_id = str(payload.get("id") or hashlib.sha256(body).hexdigest())
        event_type = str(payload.get("type") or "unknown")
        return WebhookEnvelope(event_id, event_type, payload)


class StripeBillingProvider(BillingProvider):
    name = "stripe"

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        api_base_url: str | None = None,
        timeout_seconds: int | None = None,
        price_map: dict[str, str] | None = None,
        webhook_tolerance_seconds: int | None = None,
    ) -> None:
        self.secret_key = secret_key or settings.stripe_secret_key
        self.api_base_url = (api_base_url or settings.stripe_api_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.stripe_timeout_seconds
        self.price_map = price_map or {
            "creator": settings.stripe_price_creator,
            "pro": settings.stripe_price_pro,
            "studio": settings.stripe_price_studio,
        }
        self.webhook_tolerance_seconds = webhook_tolerance_seconds or settings.billing_webhook_tolerance_seconds

    def price_reference(self, plan_code: str) -> str | None:
        return self.price_map.get(plan_code)

    def _require_key(self) -> str:
        if not self.secret_key:
            raise RuntimeError("Stripe secret key is not configured")
        return self.secret_key

    async def _request(self, method: str, path: str, *, data: list[tuple[str, str]] | None = None) -> dict[str, Any]:
        key = self._require_key()
        url = f"{self.api_base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(method, url, data=data, auth=(key, ""))
        if response.is_error:
            detail: str
            try:
                payload = response.json()
                detail = str(payload.get("error", {}).get("message") or response.text[:500])
            except ValueError:
                detail = response.text[:500]
            raise RuntimeError(f"Stripe API error ({response.status_code}): {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Stripe returned a non-JSON response") from exc

    async def create_checkout(
        self,
        *,
        customer_reference: str | None,
        organization_reference: str,
        plan_code: str,
        return_url: str,
    ) -> CheckoutSession:
        price_id = self.price_reference(plan_code)
        if not price_id:
            raise ValueError(f"No Stripe Price ID configured for plan '{plan_code}'")

        data: list[tuple[str, str]] = [
            ("mode", "subscription"),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", "1"),
            ("success_url", f"{return_url}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"),
            ("cancel_url", f"{return_url}?checkout=cancel"),
            ("client_reference_id", organization_reference),
            ("metadata[organization_id]", organization_reference),
            ("metadata[plan_code]", plan_code),
            ("subscription_data[metadata][organization_id]", organization_reference),
            ("subscription_data[metadata][plan_code]", plan_code),
        ]
        if customer_reference and customer_reference.startswith("cus_"):
            data.append(("customer", customer_reference))

        payload = await self._request("POST", "/v1/checkout/sessions", data=data)
        session_id = str(payload.get("id") or "")
        url = str(payload.get("url") or "")
        if not session_id or not url:
            raise RuntimeError("Stripe checkout response is missing id or url")
        return CheckoutSession(id=session_id, url=url, provider=self.name)

    async def cancel_subscription(self, provider_subscription_reference: str, *, at_period_end: bool) -> None:
        if not provider_subscription_reference.startswith("sub_"):
            raise ValueError("Invalid Stripe subscription reference")
        if at_period_end:
            await self._request(
                "POST",
                f"/v1/subscriptions/{provider_subscription_reference}",
                data=[("cancel_at_period_end", "true")],
            )
        else:
            await self._request("DELETE", f"/v1/subscriptions/{provider_subscription_reference}")

    def verify_webhook(self, body: bytes, signature: str | None, secret: str) -> WebhookEnvelope:
        if not signature:
            raise ValueError("Missing Stripe-Signature header")
        secrets_to_try = [item.strip() for item in settings.billing_webhook_secrets.split(",") if item.strip()]
        if secret and secret not in secrets_to_try:
            secrets_to_try.insert(0, secret)
        if not secrets_to_try:
            raise ValueError("Stripe webhook signing secret is not configured")

        timestamp: int | None = None
        candidates: list[str] = []
        for chunk in signature.split(","):
            key, sep, value = chunk.strip().partition("=")
            if not sep:
                continue
            if key == "t":
                try:
                    timestamp = int(value)
                except ValueError as exc:
                    raise ValueError("Invalid Stripe webhook timestamp") from exc
            elif key == "v1":
                candidates.append(value)
        if timestamp is None or not candidates:
            raise ValueError("Invalid Stripe-Signature header")

        now = int(datetime.now(timezone.utc).timestamp())
        if abs(now - timestamp) > self.webhook_tolerance_seconds:
            raise ValueError("Expired Stripe webhook signature")

        signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
        verified = False
        for signing_secret in secrets_to_try:
            expected = hmac.new(signing_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
            if any(hmac.compare_digest(expected, candidate) for candidate in candidates):
                verified = True
                break
        if not verified:
            raise ValueError("Invalid Stripe webhook signature")

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Invalid Stripe webhook payload") from exc
        if not isinstance(payload, dict):
            raise ValueError("Invalid Stripe webhook payload")
        event_id = str(payload.get("id") or "")
        event_type = str(payload.get("type") or "unknown")
        if not event_id:
            raise ValueError("Stripe webhook is missing event id")
        return WebhookEnvelope(event_id, event_type, payload)


def provider_from_settings(name: str) -> BillingProvider:
    if name == "mock":
        return MockBillingProvider()
    if name == "stripe":
        return StripeBillingProvider()
    raise ValueError(f"Unsupported billing provider: {name}")
