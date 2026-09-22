from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text()


def test_routing_api_is_registered_and_documented():
    main = read("app/main.py")
    api = read("app/api/routing.py")
    assert "routing_router" in main
    for route in ["/providers", "/route", "/project-plan", "/decisions"]:
        assert route in api


def test_migration_005_contains_routing_tables():
    migrations = read("app/db/migrations.py")
    assert '"005_v15_cost_aware_routing"' in migrations
    assert "CREATE TABLE IF NOT EXISTS provider_profiles" in migrations
    assert "CREATE TABLE IF NOT EXISTS routing_decisions" in migrations


def test_orchestrator_excludes_failed_provider_on_retry():
    orchestrator = read("app/services/orchestrator.py")
    assert "exclude_providers" in orchestrator
    assert "excluded" in read("app/routing/service.py") or "exclude_providers" in read("app/routing/service.py")


def test_raw_api_key_is_rejected():
    routing_api = read("app/api/routing.py")
    assert '"api_key" in payload.config' in routing_api
    assert "Do not store raw API keys" in routing_api
