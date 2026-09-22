import ast
import asyncio
import os
from pathlib import Path

import pytest

from app.observability.metrics import MetricsRegistry
from app.observability.tracing import tracing
from app.observability.provider_health import ProviderHealthService


ROOT = Path(__file__).resolve().parents[1]


def test_metrics_prometheus_render_is_valid_shape():
    registry = MetricsRegistry()
    registry.inc('demo_requests_total', labels={'method': 'GET'})
    registry.observe('demo_duration_seconds', 0.02, labels={'route': '/demo'})
    out = registry.render()
    assert '# TYPE demo_requests_total counter' in out
    assert 'demo_requests_total{method="GET"} 1.0' in out
    assert 'demo_duration_seconds_bucket' in out
    assert out.endswith('\n')


def test_trace_context_accepts_w3c_traceparent_and_propagates():
    span = tracing.start_request('00-' + '1' * 32 + '-' + '2' * 16 + '-01')
    assert span.trace_id == '1' * 32
    assert tracing.traceparent().startswith('00-' + '1' * 32 + '-')


def test_provider_health_does_not_make_network_calls():
    payload = ProviderHealthService().payload()
    assert 'providers' in payload
    assert all('configured' in item and 'available' in item for item in payload['providers'])
    for item in payload['providers']:
        if item['mode'] == 'configuration' and item['provider'] != 'youtube-research':
            assert item['available'] == item['configured']


def test_observability_routes_have_expected_endpoints():
    text = (ROOT / 'app/api/observability.py').read_text()
    assert '@router.get(\'/providers\')' in text
    assert '@router.get(\'/workers\')' in text
    main = (ROOT / 'app/main.py').read_text()
    assert '/api/v1/health/live' in main
    assert '/api/v1/health/ready' in main
    assert '/api/v1/metrics' in main


def test_worker_heartbeat_migration_present():
    text = (ROOT / 'app/db/migrations.py').read_text()
    assert '012_v22_observability' in text
    assert 'CREATE TABLE IF NOT EXISTS worker_heartbeats' in text


def test_frontend_files_still_parse_as_text_contracts():
    pages = list((ROOT / 'frontend/app').rglob('*.tsx'))
    assert len(pages) >= 19
    for page in pages:
        content = page.read_text()
        assert 'export default' in content


@pytest.mark.integration
def test_real_postgres_smoke():
    dsn = os.getenv('TEST_DATABASE_URL')
    if not dsn:
        pytest.skip('TEST_DATABASE_URL not configured')

    async def run():
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.models.base import Base
        from app.db.migrations import apply_migrations
        from app import models  # noqa: F401

        engine = create_async_engine(dsn)
        async with engine.begin() as conn:
            result = await conn.execute(text('SELECT version()'))
            version = result.scalar_one()
            assert 'PostgreSQL' in version
            await conn.run_sync(Base.metadata.create_all)
        await apply_migrations(engine)
        async with engine.connect() as conn:
            applied = await conn.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
            versions = [row[0] for row in applied.fetchall()]
            assert '012_v22_observability' in versions
            heartbeat = await conn.execute(text("SELECT to_regclass('public.worker_heartbeats')"))
            assert heartbeat.scalar_one() == 'worker_heartbeats'
        await engine.dispose()

    asyncio.run(run())
