import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.creative_director.service import CreativeDirectorService


def _project():
    return SimpleNamespace(id=uuid4())


def test_director_selects_replace_visual_for_low_alignment():
    analysis = {
        "score": 60,
        "scene_reports": [
            {
                "scene": 2,
                "narration_visual_alignment": 0.3,
                "relevance_score": 0.6,
                "clarity_score": 0.8,
                "issues": ["narration mismatch"],
                "recommendations": ["replace visual"],
            }
        ],
    }
    result = asyncio.run(CreativeDirectorService(llm_provider="mock").build_plan(project=_project(), analysis=analysis, max_changes=2))
    assert result["status"] == "READY"
    assert result["changes"][0]["action"] == "replace_visual"
    assert result["execution"]["automatic"] == 1


def test_director_tighten_is_bounded():
    analysis = {
        "scene_reports": [
            {
                "scene": 1,
                "narration_visual_alignment": 0.9,
                "relevance_score": 0.95,
                "clarity_score": 0.95,
                "issues": ["repetitive pacing"],
                "recommendations": ["tighten"],
            }
        ]
    }
    result = asyncio.run(CreativeDirectorService(llm_provider="mock").build_plan(project=_project(), analysis=analysis, max_changes=3))
    change = result["changes"][0]
    assert change["action"] == "tighten"
    assert 0.25 <= change["parameters"]["duration_multiplier"] <= 1.0


def test_director_never_invents_scene_numbers():
    analysis = {"scene_reports": [{"scene": 1, "narration_visual_alignment": 0.2, "issues": ["mismatch"]}]}
    class FakeLLM:
        name = "fake"
        async def generate_json(self, *, system, user):
            return {"changes": [{"scene": 99, "action": "replace_visual", "priority": 1.0, "confidence": 0.9, "parameters": {}}]}
    service = CreativeDirectorService.__new__(CreativeDirectorService)
    service.llm = FakeLLM()
    result = asyncio.run(service.build_plan(project=_project(), analysis=analysis, max_changes=3))
    assert result["status"] == "NO_CHANGE"
    assert result["changes"] == []


def test_creative_reedit_api_does_not_accept_browser_provider_credentials():
    text = Path("app/api/creative.py").read_text()
    assert "api_key" not in text[text.find("class DirectorPlanRequest"):text.find("def _serialize_director")]
    assert "llm_config" not in text[text.find("class DirectorPlanRequest"):text.find("def _serialize_director")]


def test_creative_director_model_and_migration_contract():
    model = Path("app/models/creative_director.py").read_text()
    migration = Path("app/db/migrations.py").read_text()
    assert "creative_director_decisions" in model
    assert "023_v35_creative_director" in migration


def test_render_executor_rejects_manual_review(tmp_path):
    # The renderer must never interpret manual_review as an automatic visual replacement.
    from app.creative_intelligence.service import TargetedReEditService
    source = tmp_path / "missing-source.mp4"
    project = SimpleNamespace(id=uuid4(), data={"editor": {"output_path": str(source)}}, channel_id=uuid4())
    service = TargetedReEditService.__new__(TargetedReEditService)
    service.output_dir = tmp_path
    service.image_provider = None
    try:
        asyncio.run(service.render_patch(source_project=project, revision_project_id=str(uuid4()), scene_patches=[{"scene": 1, "action": "manual_review"}]))
    except FileNotFoundError:
        pass
    # The explicit action contract is enforced in the service source as a defense-in-depth check.
    source_text = Path("app/creative_intelligence/service.py").read_text()
    assert 'if action not in {"replace_visual", "tighten"}' in source_text


def test_tighten_action_shortens_rendered_scene(tmp_path):
    from app.creative_intelligence.service import TargetedReEditService, probe_duration
    from app.media.mock import MockVisualAssetProvider
    from subprocess import run

    source = tmp_path / "source.mp4"
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "2.0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)]
    proc = run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-1000:]
    project = SimpleNamespace(
        id=uuid4(),
        data={
            "editor": {"output_path": str(source)},
            "scene_director": {"scenes": [
                {"scene": 1, "duration": 2.0, "visual_prompt": "keep the existing visual"},
            ]},
        },
        channel_id=uuid4(),
    )
    service = TargetedReEditService(str(tmp_path), image_provider=MockVisualAssetProvider())
    result = asyncio.run(service.render_patch(
        source_project=project,
        revision_project_id=str(uuid4()),
        scene_patches=[{"scene": 1, "action": "tighten", "parameters": {"duration_multiplier": 0.7}}],
    ))
    assert result["duration_overrides"] == {"1": 0.7}
    assert result["patched_scenes"] == [1]
    assert result["duration_seconds"] < 1.7
