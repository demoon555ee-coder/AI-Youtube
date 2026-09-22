from pathlib import Path

def test_v34_creative_static_contracts():
    service = Path("app/creative_intelligence/service.py").read_text()
    api = Path("app/api/creative.py").read_text()
    assert "CreativeIntelligenceService" in service
    assert "TargetedReEditService" in service
    assert "narration_visual_alignment" in service
    assert 'prefix="/api/v1/creative"' in api
    assert '/projects/{project_id}/reedit' in api


def test_v34_vision_responses_contract():
    text = Path("app/vision/openai.py").read_text()
    assert "/responses" in text
    assert '"type": "input_image"' in text
    assert '"type": "input_text"' in text


def test_v34_model_and_migration_contract():
    model = Path("app/models/creative.py").read_text()
    migration = Path("app/db/migrations.py").read_text()
    assert "creative_analyses" in model
    assert "022_v34_creative_intelligence" in migration
