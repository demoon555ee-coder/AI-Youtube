from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _normalize_database_url(database_url: str) -> tuple[URL, bool]:
    url = make_url(database_url)
    if url.drivername in {"postgresql", "postgres"}:
        url = url.set(drivername="postgresql+asyncpg")

    # Keep Neon's pooler endpoint when it is provided by DATABASE_URL.
    # The configured Railway credential is valid on the pooler endpoint;
    # rewriting it to the direct endpoint can break authentication.

    # asyncpg does not consume libpq's sslmode/channel_binding URL parameters.
    query = dict(url.query)
    sslmode = str(query.pop("sslmode", "")).lower()
    query.pop("channel_binding", None)
    url = url.set(query=query)

    use_ssl = sslmode in {"require", "verify-ca", "verify-full"}
    return url, use_ssl


database_url, _use_ssl = _normalize_database_url(settings.database_url)
connect_args = {
    "ssl": True,
    "timeout": 10,
    "statement_cache_size": 0,
} if _use_ssl else {
    "timeout": 10,
    "statement_cache_size": 0,
}

engine = create_async_engine(
    database_url,
    connect_args=connect_args,
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session
