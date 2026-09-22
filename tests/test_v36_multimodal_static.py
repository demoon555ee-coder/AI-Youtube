from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v36_version_and_migration_contract():
    config = (ROOT / "app/config.py").read_text()
    migration = (ROOT / "app/db/migrations.py").read_text()
    assert 'app_version: str = "4.2.1"' in config
    assert "024_v36_multimodal_production_graph" in migration
    assert "production_multimodal_graphs" in migration


def test_v36_multimodal_api_and_router_contract():
    api = (ROOT / "app/api/multimodal.py").read_text()
    main = (ROOT / "app/main.py").read_text()
    assert 'prefix="/api/v1/multimodal"' in api
    assert '/projects/{project_id}/preflight' in api
    assert '/projects/{project_id}/analyze' in api
    assert 'permission_dependency("content:write")' in api
    assert 'app.include_router(multimodal_router)' in main


def test_v36_orchestrator_runs_preflight_before_production():
    text = (ROOT / "app/services/orchestrator.py").read_text()
    production = text[text.index('if name == "production":'):text.index('elif name == "research":')]
    assert 'MultimodalProductionGraphService' in production
    assert 'build_preflight' in production
    assert 'multimodal_preflight_hard_fail' in production
