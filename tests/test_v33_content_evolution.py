from pathlib import Path
import hashlib


def test_v33_models_and_migration_contract():
    from app.models import ContentVersion, ContentArtifact, VideoProject
    assert ContentVersion.__tablename__ == "content_versions"
    assert ContentArtifact.__tablename__ == "content_artifacts"
    assert hasattr(VideoProject, "content_root_id")
    assert hasattr(VideoProject, "parent_project_id")
    assert hasattr(VideoProject, "revision_number")
    text = Path("app/db/migrations.py").read_text()
    assert "021_v33_content_evolution" in text
    assert "trg_video_projects_content_root" in text
    assert "trg_video_projects_baseline_version" in text


def test_v33_evolution_plan_for_retention():
    from app.evolution.service import build_evolution_plan
    plan = build_evolution_plan(metric="retention", delta_pct=-31.5, evidence={"source": "analytics"})
    assert plan["preserve_topic"] is True
    assert plan["do_not_modify_source"] is True
    assert "move_first_reveal_earlier" in plan["sections"]
    assert plan["observed_delta_pct"] == -31.5


def test_v33_evolution_plan_for_ctr():
    from app.evolution.service import build_evolution_plan
    plan = build_evolution_plan(metric="ctr", delta_pct=-22, evidence={})
    assert plan["experiment_dimension"] == "title_or_thumbnail"
    assert "packaging" in plan


def test_v33_artifact_hash_is_streaming_and_sha256(tmp_path):
    from app.evolution.service import ContentEvolutionService
    path = tmp_path / "large.bin"
    payload = b"abc123" * 200000
    path.write_bytes(payload)
    assert ContentEvolutionService._sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_v33_orchestrator_passes_evolution_context():
    text = Path("app/services/orchestrator.py").read_text()
    assert 'evolution = project_data.get("evolution") or {}' in text
    assert '"evolution": evolution' in text
    assert 'register_project_artifacts' in text
    assert 'version_row.status = "READY_TO_PUBLISH"' in text


def test_v33_evolution_api_contract():
    text = Path("app/api/evolution.py").read_text()
    assert '@router.post("/projects/{project_id}/revisions"' in text
    assert '@router.get("/projects/{project_id}/versions")' in text
    assert '@router.get("/projects/{project_id}/artifacts")' in text
    assert "auto_run" in text
    assert "parent_project_id" in text


def test_v33_main_registers_evolution_router():
    text = Path("app/main.py").read_text()
    assert "evolution_router" in text
    assert "app.include_router(evolution_router)" in text


def test_v33_frontend_exposes_evolution_page():
    assert Path("frontend/app/evolution/page.tsx").exists()
    shell = Path("frontend/components/Shell.tsx").read_text()
    assert '["Content Evolution", "/evolution"]' in shell


def test_v33_alert_revision_requires_published_source_contract():
    text = Path("app/api/evolution.py").read_text()
    assert "Publication.project_id == source.id" in text
    assert "Publication.youtube_video_id" in text
    text2 = Path("app/api/postpublish.py").read_text()
    assert "Alert is not linked to a published source project" in text2


def test_v33_postpublish_ui_can_start_revision():
    text = Path("frontend/app/post-publish/page.tsx").read_text()
    assert 'create-revision' in text
    assert 'Create improved version' in text
