from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx

from app.config import settings


def retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def should_retry_response(response: httpx.Response) -> bool:
    return response.status_code == 429 or 500 <= response.status_code <= 599


async def request_with_retry(
    operation: Callable[[], Awaitable[httpx.Response]],
    *,
    max_retries: int | None = None,
    base_seconds: float | None = None,
    max_seconds: float | None = None,
) -> httpx.Response:
    retries = settings.llm_max_retries if max_retries is None else max(0, max_retries)
    base = settings.provider_retry_base_seconds if base_seconds is None else max(0.0, base_seconds)
    cap = settings.provider_retry_max_seconds if max_seconds is None else max(0.0, max_seconds)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await operation()
            if not should_retry_response(response) or attempt >= retries:
                return response
            retry_delay = retry_after_seconds(response)
            delay = retry_delay if retry_delay is not None else min(cap, base * (2 ** attempt))
            await asyncio.sleep(delay)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            delay = min(cap, base * (2 ** attempt))
            await asyncio.sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError("HTTP request retry loop exited unexpectedly")
