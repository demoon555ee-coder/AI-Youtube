from __future__ import annotations

import asyncio
import os

import asyncpg
from sqlalchemy.engine import make_url


async def main() -> None:
    url = make_url(os.environ["DATABASE_URL"])
    host = url.host.replace("-pooler.", ".") if url.host else url.host
    print(f"DB_PROBE_HOST={host}", flush=True)
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=host,
        port=url.port or 5432,
        database=url.database,
        ssl=True,
        timeout=10,
        statement_cache_size=0,
    )
    try:
        result = await conn.fetchval("SELECT 1")
        print(f"DB_PROBE_RESULT={result}", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
