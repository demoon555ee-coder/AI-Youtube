from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v35_version_and_migration():
    config = (ROOT / "app/config.py").read_text()
    migration = (ROOT / "app/db/migrations.py").read_text()
    assert 'app_version: str = "4.2.4"' in config
    assert "023_v35_creative_director" in migration


def test_v35_creative_director_contract():
    service = (ROOT / "app/creative_director/service.py").read_text()
    api = (ROOT / "app/api/creative.py").read_text()
    assert "CreativeDirectorService" in service
    assert "replace_visual" in service
    assert "tighten" in service
    assert '/projects/{project_id}/director-plan' in api


def test_v35_no_browser_provider_secrets():
    api = (ROOT / "app/api/creative.py").read_text()
    start = api.index('class DirectorPlanRequest')
    end = api.index('def _serialize_director')
    block = api[start:end]
    assert 'api_key' not in block
    assert 'base_url' not in block
