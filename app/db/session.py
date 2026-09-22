from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _normalize_database_url(database_url: str) -> tuple[URL, bool]:
    url = make_url(database_url)

    # The application uses SQLAlchemy's asyncpg driver. Accept plain Neon/Postgres
    # URLs as well as explicit +asyncpg URLs without requiring psycopg2.
    if url.drivername in {"postgresql", "postgres"}:
        url = url.set(drivername="postgresql+asyncpg")

    # Neon/libpq URLs can contain parameters that asyncpg does not accept as
    # connect() keyword arguments. Preserve the TLS requirement natively.
    query = dict(url.query)
    sslmode = str(query.pop("sslmode", "")).lower()
    query.pop("channel_binding", None)
    url = url.set(query=query)

    use_ssl = sslmode in {"require", "verify-ca", "verify-full"}
    return url, use_ssl


database_url, _use_ssl = _normalize_database_url(settings.database_url)
engine = create_async_engine(
    database_url,
    connect_args={"ssl": True} if _use_ssl else {},
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session
