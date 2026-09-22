from __future__ import annotations

import asyncio
import os
import sys

import httpx


async def check() -> int:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key.startswith("sk_test_"):
        print("ERROR STRIPE_SECRET_KEY must be a test-mode key starting with sk_test_")
        return 2
    base = os.getenv("STRIPE_API_BASE_URL", "https://api.stripe.com").rstrip("/")
    timeout = float(os.getenv("STRIPE_TIMEOUT_SECONDS", "20"))
    ids = {
        "creator": os.getenv("STRIPE_PRICE_CREATOR", ""),
        "pro": os.getenv("STRIPE_PRICE_PRO", ""),
        "studio": os.getenv("STRIPE_PRICE_STUDIO", ""),
    }
    missing = [code for code, value in ids.items() if not value]
    if missing:
        print(f"ERROR missing Stripe test Price IDs: {', '.join(missing)}")
        return 2

    async with httpx.AsyncClient(timeout=timeout, auth=(key, "")) as client:
        for code, price_id in ids.items():
            response = await client.get(f"{base}/v1/prices/{price_id}")
            if response.is_error:
                print(f"ERROR {code}: Stripe returned HTTP {response.status_code}")
                return 1
            payload = response.json()
            if payload.get("id") != price_id:
                print(f"ERROR {code}: Stripe price id mismatch")
                return 1
            if not payload.get("active"):
                print(f"ERROR {code}: Stripe test price is inactive")
                return 1
            recurring = payload.get("recurring") or {}
            if recurring.get("interval") != "month":
                print(f"ERROR {code}: configured price is not monthly recurring")
                return 1
    print("stripe_sandbox_read_only_check=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
