from app.db.session import _normalize_database_url


def test_normalize_database_url_preserves_neon_pooler_host():
    raw = (
        "postgresql://user:pass@ep-example-pooler.c-6.eu-central-1.aws.neon.tech/"
        "neondb?sslmode=require&channel_binding=require"
    )

    url, use_ssl = _normalize_database_url(raw)

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "ep-example-pooler.c-6.eu-central-1.aws.neon.tech"
    assert "sslmode" not in url.query
    assert "channel_binding" not in url.query
    assert use_ssl is True
