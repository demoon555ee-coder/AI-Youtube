from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _normalize_database_url(database_url: str) -> URL:
    url = make_url(database_url)

    # The application uses SQLAlchemy's asyncpg driver. Accept plain Neon/Postgres
    # URLs as well as explicit +asyncpg URLs so deployment environments can use
    # the provider's native DATABASE_URL without requiring psycopg2.
    if url.drivername in {"postgresql", "postgres"}:
        url = url.set(drivername="postgresql+asyncpg")

    # Neon CLI connection strings may include channel_binding=require. The
    # installed asyncpg/SQLAlchemy stack does not accept that query argument,
    # while sslmode=require still enforces TLS for this deployment.
    query = dict(url.query)
    query.pop("channel_binding", None)
    url = url.set(query=query)
    return url


engine = create_async_engine(
    _normalize_database_url(settings.database_url),
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session
