from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Portfolio, ProviderCircuitState


class ProviderReliabilityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _state(self, portfolio_id, service: str, provider: str, *, lock: bool = False) -> ProviderCircuitState:
        key = {"portfolio_id": portfolio_id, "service": service, "provider": provider}
        # Avoid a unique-key race when two workers encounter a provider for the first time.
        stmt = insert(ProviderCircuitState).values(**key).on_conflict_do_nothing(
            index_elements=["portfolio_id", "service", "provider"]
        )
        await self.db.execute(stmt)
        query = select(ProviderCircuitState).where(
            ProviderCircuitState.portfolio_id == portfolio_id,
            ProviderCircuitState.service == service,
            ProviderCircuitState.provider == provider,
        )
        if lock:
            query = query.with_for_update()
        row = await self.db.scalar(query)
        if row is None:
            raise RuntimeError("Provider circuit state could not be initialized")
        return row

    async def can_route(self, portfolio_id, service: str, provider: str) -> bool:
        now = datetime.utcnow()
        row = await self._state(portfolio_id, service, provider, lock=True)
        if row.state == "CLOSED":
            return True
        if row.state == "OPEN":
            if row.next_probe_at and row.next_probe_at > now:
                return False
            row.state = "HALF_OPEN"
            row.half_open_until = now + timedelta(seconds=settings.provider_half_open_seconds)
            row.metadata_json = {**(row.metadata_json or {}), "probe_acquired_at": now.isoformat()}
            return True
        if row.state == "HALF_OPEN":
            if row.half_open_until and row.half_open_until > now:
                return False
            row.half_open_until = now + timedelta(seconds=settings.provider_half_open_seconds)
            return True
        row.state = "CLOSED"
        return True

    async def record_success(self, portfolio_id, service: str, provider: str, *, latency_ms: float | None = None) -> None:
        now = datetime.utcnow()
        row = await self._state(portfolio_id, service, provider, lock=True)
        row.success_count += 1
        row.failure_count = 0
        row.state = "CLOSED"
        row.opened_at = None
        row.next_probe_at = None
        row.half_open_until = None
        row.last_success_at = now
        row.last_error = None
        meta = dict(row.metadata_json or {})
        if latency_ms is not None:
            meta["last_latency_ms"] = round(float(latency_ms), 2)
        row.metadata_json = meta
        await self.db.flush()

    async def record_failure(self, portfolio_id, service: str, provider: str, error: str) -> None:
        now = datetime.utcnow()
        row = await self._state(portfolio_id, service, provider, lock=True)
        row.failure_count += 1
        row.last_failure_at = now
        row.last_error = str(error)[:2000]
        if row.state == "HALF_OPEN" or row.failure_count >= settings.provider_failure_threshold:
            row.state = "OPEN"
            row.opened_at = now
            row.next_probe_at = now + timedelta(seconds=settings.provider_circuit_cooldown_seconds)
            row.half_open_until = None
        else:
            row.state = "CLOSED"
        await self.db.flush()

    async def snapshot(self, portfolio_id) -> list[ProviderCircuitState]:
        rows = await self.db.execute(select(ProviderCircuitState).where(ProviderCircuitState.portfolio_id == portfolio_id).order_by(ProviderCircuitState.service, ProviderCircuitState.provider))
        return list(rows.scalars().all())


def is_transient_provider_error(exc: Exception) -> bool:
    """Return True for errors likely caused by temporary provider availability issues."""
    import httpx
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    text = str(exc).lower()
    transient_markers = ("429", "rate limit", "too many requests", "502", "503", "504", "timed out", "timeout", "temporarily unavailable", "network")
    return any(marker in text for marker in transient_markers)
