from app.models import ResearchSnapshot, TrendEvent
from app.trends.diff import build_topic_signals, topic_key_from_title


def test_topic_key_normalizes_and_removes_common_words():
    key = topic_key_from_title("How AI Agents Are Changing Software Development")
    assert "agents" in key
    assert "software" in key
    assert "how" not in key.split("+")


def test_topic_signals_are_sorted_by_signal():
    results = [
        {"id": "1", "title": "AI Agents 2026", "views": 1_000_000, "likes": 30_000, "comments": 2_000},
        {"id": "2", "title": "How to build an AI agent", "views": 100, "likes": 1, "comments": 0},
    ]
    rows = build_topic_signals(results)
    assert rows
    assert rows[0]["signal"] >= rows[-1]["signal"]
    assert all("topic_key" in row and "signal" in row for row in rows)


def test_v19_models_are_exported_and_named_correctly():
    assert ResearchSnapshot.__tablename__ == "research_snapshots"
    assert TrendEvent.__tablename__ == "trend_events"


def test_v19_migration_is_last_and_creates_trend_tables():
    from app.db.migrations import MIGRATIONS
    versions = [name for name, _ in MIGRATIONS]
    assert "009_v19_trend_diff" in versions
    sql = dict(MIGRATIONS)["009_v19_trend_diff"]
    assert "CREATE TABLE IF NOT EXISTS research_snapshots" in sql
    assert "CREATE TABLE IF NOT EXISTS trend_events" in sql


def test_v19_api_is_registered():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "app/api/trends.py").read_text()
    main = (root / "app/main.py").read_text()
    assert 'prefix="/api/v1/trends"' in text
    assert 'app.include_router(trends_router)' in main
    assert 'version=settings.app_version' in main


def test_graph_scan_persists_trend_hook():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "app/research/graph_service.py").read_text()
    assert "TrendDiffService" in text
    assert "record_snapshot" in text
    assert '"trend": trend' in text
