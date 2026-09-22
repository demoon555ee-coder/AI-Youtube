from app.opportunity_intelligence.service import _clamp, _overlap, ACTION_BY_EVENT
from app.db.migrations import _split_sql, MIGRATIONS


def test_opportunity_score_helpers():
    assert _clamp(-1) == 0
    assert _clamp(2) == 1
    assert _overlap("AI video tools", "Best AI video tools") > 0.3
    assert ACTION_BY_EVENT["RISING"] == "EXPLORE_NOW"


def test_migration_order_and_new_version():
    versions = [v for v, _ in MIGRATIONS]
    assert versions == sorted(versions, key=lambda x: int(x.split("_", 1)[0]))
    assert "010_v20_opportunity_intelligence" in versions


def test_postgres_splitter_preserves_dollar_quoted_do_block():
    sql = """
    ALTER TABLE example ADD COLUMN IF NOT EXISTS name TEXT;

    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'x') THEN
            ALTER TABLE example ADD CONSTRAINT x CHECK (name <> '');
        END IF;
    END $$;

    CREATE INDEX IF NOT EXISTS ix_example_name ON example(name);
    """
    statements = _split_sql(sql)
    assert len(statements) == 3
    assert statements[1].startswith("DO $$")
    assert statements[1].endswith("END $$")


def test_migration_sql_is_not_broken_by_blank_lines():
    for version, sql in MIGRATIONS:
        statements = _split_sql(sql)
        assert statements, version
        assert all(statement.strip() for statement in statements)
