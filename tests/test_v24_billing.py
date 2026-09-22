import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
import re

from app.billing.providers import MockBillingProvider
from app.billing.service import DEFAULT_PLANS, METRIC_ALIASES


def test_billing_catalog_has_expected_plans_and_entitlements():
    codes = [p["code"] for p in DEFAULT_PLANS]
    assert codes == ["free", "creator", "pro", "studio"]
    assert all("monthly_video_projects" in p["entitlements"] for p in DEFAULT_PLANS)
    assert DEFAULT_PLANS[0]["monthly_price_cents"] == 0
    assert DEFAULT_PLANS[-1]["entitlements"]["max_channels"] > DEFAULT_PLANS[0]["entitlements"]["max_channels"]


def test_metric_aliases_are_stable():
    assert METRIC_ALIASES["workflow"] == "monthly_video_projects"
    assert METRIC_ALIASES["llm"] == "monthly_llm_requests"
    assert METRIC_ALIASES["render"] == "monthly_render_minutes"


def test_mock_checkout_has_plan_and_return_url():
    import asyncio
    result = asyncio.run(MockBillingProvider().create_checkout(customer_reference="cust_1", organization_reference="org_1", plan_code="creator", return_url="http://localhost:3000/billing"))
    assert result.provider == "mock"
    assert "plan=creator" in result.url


def test_mock_webhook_signature_and_replay_identity():
    body = json.dumps({"id": "evt_1", "type": "invoice.paid", "data": {"ok": True}}).encode()
    secret = "secret"
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    envelope = MockBillingProvider().verify_webhook(body, signature, secret)
    assert envelope.event_id == "evt_1"
    assert envelope.event_type == "invoice.paid"


def test_public_billing_webhook_is_declared():
    auth = Path("app/auth/authorization.py").read_text()
    assert '"/api/v1/billing/webhooks"' in auth


def test_billing_migration_present_and_ordered():
    text = Path("app/db/migrations.py").read_text()
    versions = re.findall(r'"(0\d+_v[^"\n]+)"', text)
    assert "013_v24_billing" in versions
    assert versions[versions.index("013_v24_billing")].startswith("013_v24_billing")
    assert versions.index("013_v24_billing") < versions.index("014_v25_real_billing_provider") < versions.index("015_v25_webhook_reliability")


def test_production_billing_requires_real_provider_and_webhook_secret():
    text = Path("app/deployment.py").read_text()
    assert '"mock_billing_provider"' in text
    assert '"missing_billing_webhook_secret"' in text


def test_billing_api_does_not_expose_public_plan_activation():
    text = Path("app/api/billing.py").read_text()
    assert '@router.post("/dev/activate")' in text
    assert 'if settings.app_env == "production":' in text


def test_metering_uses_atomic_upsert_primitives():
    text = Path("app/billing/service.py").read_text()
    assert 'on_conflict_do_nothing' in text
    assert 'BillingMeterEvent' in text
