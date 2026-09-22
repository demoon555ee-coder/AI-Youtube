from __future__ import annotations

import os

import pytest


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + url.split("://", 1)[1]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.split("://", 1)[1]
    raise ValueError(f"Unsupported PostgreSQL URL returned by Testcontainers: {url}")


@pytest.fixture(scope="session")
def postgres_url():
    provided = os.getenv("TEST_DATABASE_URL")
    if provided:
        yield provided
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        if os.getenv("REQUIRE_INTEGRATION", "false").lower() == "true":
            raise
        pytest.skip(f"testcontainers is unavailable: {exc}")

    image = os.getenv("TEST_POSTGRES_IMAGE", "postgres:16")
    container = PostgresContainer(image)
    try:
        container.start()
    except Exception as exc:
        if os.getenv("REQUIRE_INTEGRATION", "false").lower() == "true":
            raise
        pytest.skip(f"Docker/Testcontainers unavailable: {exc}")

    try:
        yield _asyncpg_url(container.get_connection_url())
    finally:
        container.stop()
