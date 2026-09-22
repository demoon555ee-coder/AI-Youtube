from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


EXPECTED_SCHEMA = "034_lock_public_data_api_roles"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env.supabase-staging"


def _load_database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'")
    if value:
        return value
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or not line.startswith("DATABASE_URL="):
                continue
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


async def main() -> None:
    database_url = _load_database_url()
    if not database_url:
        raise SystemExit(f"DATABASE_URL is required (or set it in {ENV_FILE.name})")
    if "REPLACE_WITH_DATABASE_PASSWORD" in database_url:
        raise SystemExit("Set the real staging database password in .env.supabase-staging before running this check")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+asyncpg://" + database_url[len("postgresql://"):]
    elif database_url.startswith("postgres://"):
        database_url = "postgresql+asyncpg://" + database_url[len("postgres://"):]

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            database, version = (
                await conn.execute(
                    text("SELECT current_database(), version()")
                )
            ).one()
            schema_version = (
                await conn.execute(
                    text("SELECT max(version) FROM schema_migrations")
                )
            ).scalar_one_or_none()
            tables = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema='public'"
                    )
                )
            ).scalar_one()
            grants = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.role_table_grants "
                        "WHERE table_schema='public' "
                        "AND grantee IN ('anon','authenticated')"
                    )
                )
            ).scalar_one()

            print(f"database={database}")
            print(f"server={version.splitlines()[0]}")
            print(f"schema_version={schema_version}")
            print(f"public_tables={tables}")
            print(f"anon_authenticated_table_grants={grants}")

            if schema_version != EXPECTED_SCHEMA:
                raise SystemExit(
                    f"Schema mismatch: expected {EXPECTED_SCHEMA}, got {schema_version}"
                )
            if int(grants) != 0:
                raise SystemExit(
                    "Security check failed: anon/authenticated still have table grants"
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
