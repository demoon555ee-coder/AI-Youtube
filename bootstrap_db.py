import asyncio
from app.db.session import engine
from app.models.base import Base
from app import models  # noqa: F401
from app.db.migrations import apply_migrations, MIGRATIONS

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_migrations(engine)
    print("schema bootstrapped, latest:", MIGRATIONS[-1][0])
    await engine.dispose()

asyncio.run(main())
