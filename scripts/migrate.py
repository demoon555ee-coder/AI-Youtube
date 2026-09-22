from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db.migrations import apply_migrations, MIGRATIONS
from app.db.session import engine
from app.deployment import assert_production_settings
from app.models import Base


async def main() -> None:
    if os.getenv("MIGRATION_ONLY", "false").lower() != "true":
        assert_production_settings()

    if os.getenv("MIGRATION_BOOTSTRAP_BASE_SCHEMA", "false").lower() == "true":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    await apply_migrations(engine)
    print(f"schema_current={MIGRATIONS[-1][0]}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
