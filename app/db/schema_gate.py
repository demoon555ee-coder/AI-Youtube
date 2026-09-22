from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.migrations import MIGRATIONS

LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]


async def current_schema_version(engine: AsyncEngine) -> str | None:
    async with engine.connect() as conn:
        exists = await conn.execute(text("SELECT to_regclass('public.schema_migrations')"))
        if exists.scalar_one_or_none() is None:
            return None
        result = await conn.execute(text("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"))
        return result.scalar_one_or_none()


async def schema_is_current(engine: AsyncEngine) -> tuple[bool, str | None, str]:
    current = await current_schema_version(engine)
    return current == LATEST_SCHEMA_VERSION, current, LATEST_SCHEMA_VERSION
