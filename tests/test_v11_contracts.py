from pathlib import Path


def test_v11_routes_and_models_are_registered():
    main = Path("app/main.py").read_text(encoding="utf-8")
    models = Path("app/models/__init__.py").read_text(encoding="utf-8")
    assert "experiments_router" in main
    assert "research_router" in main
    assert "ContentExperiment" in models
    assert "ResearchReport" in models


def test_scene_director_is_a_durable_workflow_step():
    engine = Path("app/workflows/engine.py").read_text(encoding="utf-8")
    assert '("scene_director", "DIRECTING_SCENES")' in engine


def test_real_provider_configuration_is_exposed():
    config = Path("app/config.py").read_text(encoding="utf-8")
    assert "research_provider" in config
    assert "llm_max_retries" in config


def test_migration_runner_is_idempotent_by_version():
    text = Path("app/db/migrations.py").read_text(encoding="utf-8")
    assert 'CREATE TABLE IF NOT EXISTS schema_migrations' in text
    assert 'WHERE version=:version' in text
    assert '001_v11' in text


def test_targeted_analytics_query_does_not_request_reporting_only_reach_metrics():
    text = Path("app/services/youtube_client.py").read_text(encoding="utf-8")
    assert "videoThumbnailImpressions" not in text
    assert "videoThumbnailImpressionsClickRate" not in text
