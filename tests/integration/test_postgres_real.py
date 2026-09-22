from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db.migrations import MIGRATIONS, apply_migrations
from app.db.schema_gate import schema_is_current
from app.models import (
    ApiKey,
    BillingPlan,
    Channel,
    Membership,
    Organization,
    User,
    VideoProject,
    WorkflowRun,
)
from app.models.base import Base


pytestmark = pytest.mark.integration


async def _fresh_engine(postgres_url: str):
    engine = create_async_engine(postgres_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_migrations(engine)
    return engine


async def test_real_postgres_schema_and_core_write_path(postgres_url):
    engine = await _fresh_engine(postgres_url)
    try:
        current, applied, expected = await schema_is_current(engine)
        assert current is True
        assert applied == expected == MIGRATIONS[-1][0]

        async with engine.begin() as db:
            org = Organization(name="Integration Org", slug=f"integration-{uuid.uuid4().hex[:10]}")
            user = User(email=f"integration-{uuid.uuid4().hex[:10]}@example.com", password_hash="test-hash", name="Integration User")
            db.add_all([org, user])
            await db.flush()
            db.add(Membership(organization_id=org.id, user_id=user.id, role="owner"))
            channel = Channel(
                owner_id=str(user.id), organization_id=org.id,
                name="Integration Channel", language="en", niche="testing", timezone="Europe/Brussels",
            )
            db.add(channel)
            await db.flush()
            project = VideoProject(channel_id=channel.id, topic="Real PostgreSQL integration")
            db.add(project)
            await db.flush()
            db.add(WorkflowRun(
                project_id=project.id,
                status="QUEUED",
                idempotency_key=f"integration:{uuid.uuid4().hex}",
                current_step=None,
            ))
            db.add(BillingPlan(
                code=f"integration-{uuid.uuid4().hex[:8]}",
                name="Integration Plan",
                monthly_price_cents=100,
                currency="USD",
                entitlements={"max_channels": 2},
            ))

        async with engine.connect() as db:
            tables = [
                "users", "organizations", "memberships", "channels", "video_projects",
                "workflow_runs", "billing_plans", "schema_migrations",
            ]
            for table in tables:
                result = await db.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"})
                assert result.scalar_one() == table

            project_count = await db.scalar(text("SELECT count(*) FROM video_projects"))
            assert int(project_count or 0) >= 1
    finally:
        await engine.dispose()


async def test_real_postgres_constraints_are_enforced(postgres_url):
    engine = await _fresh_engine(postgres_url)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with Session() as db:
            org = Organization(name="Constraint Org", slug=f"constraint-{uuid.uuid4().hex[:10]}")
            user = User(email=f"constraint-{uuid.uuid4().hex[:10]}@example.com", password_hash="x")
            db.add_all([org, user])
            await db.flush()
            db.add(Membership(organization_id=org.id, user_id=user.id, role="owner"))
            await db.flush()
            db.add(ApiKey(
                organization_id=org.id,
                created_by_user_id=user.id,
                name="integration",
                prefix="ytai_",
                key_hash=f"{uuid.uuid4().hex}{uuid.uuid4().hex}",
                scopes=["content:read"],
                expires_at=datetime.utcnow() + timedelta(days=1),
            ))
            await db.commit()

        async with Session() as db:
            duplicate = select(Membership).where(Membership.organization_id == org.id, Membership.user_id == user.id)
            existing = await db.scalar(duplicate)
            assert existing is not None
            db.add(Membership(organization_id=org.id, user_id=user.id, role="member"))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        await engine.dispose()
