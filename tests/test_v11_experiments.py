from datetime import datetime
from types import SimpleNamespace

import pytest

from app.experiments.engine import ExperimentEngine


def test_experiment_spec_selects_dimension_from_optimization_report():
    report = SimpleNamespace(
        actions=["Test an alternative thumbnail"],
        hypotheses=["A stronger thumbnail may improve click-through"],
    )
    project = SimpleNamespace(
        topic="AI Agents",
        data={"title": "AI Agents in 2027", "hook": "The obvious answer is wrong."},
    )
    spec = ExperimentEngine().build_from_optimization(report=report, project=project)
    assert spec["dimension"] == "thumbnail"
    assert set(spec["variants"]) >= {"control", "variant_a", "variant_b"}
    assert spec["decision_rule"]["primary_metric"] == "ctr"


def test_experiment_spec_selects_hook_for_opening_signal():
    report = SimpleNamespace(actions=["Shorten the opening"], hypotheses=[])
    project = SimpleNamespace(topic="Robotics", data={"title": "Robotics", "hook": "Old hook"})
    spec = ExperimentEngine().build_from_optimization(report=report, project=project)
    assert spec["dimension"] == "hook"
    assert spec["variants"]["variant_a"]["hook"] != "Old hook"


@pytest.mark.asyncio
async def test_scene_director_mock_is_deterministic():
    from app.agents.scene_director import SceneDirectorAgent
    from app.providers.mock import MockLLMProvider

    result = await SceneDirectorAgent(MockLLMProvider()).run({
        "storyboard": {"scenes": [
            {"scene": 1, "duration": 4, "narration": "A", "visual_prompt": "A visual"},
            {"scene": 2, "duration": 6, "narration": "B", "visual_prompt": "B visual"},
        ]}
    })
    assert len(result["scenes"]) == 2
    assert result["scenes"][0]["asset_type"] in {"image", "video", "graphic"}
    assert result["scenes"][1]["scene"] == 2
    assert result["scenes"][1]["duration"] == 6


def test_experiment_thumbnail_variants_use_physical_artifacts():
    from app.experiments.engine import ExperimentEngine

    report = SimpleNamespace(
        actions=["Test an alternative thumbnail"],
        hypotheses=["A different text treatment may improve click-through"],
    )
    project = SimpleNamespace(
        topic="AI Agents",
        data={
            "title": "AI Agents",
            "hook": "See the reason",
            "thumbnail": {
                "variants": [
                    {"variant_id": "control", "path": "/output/p/thumbnail.png", "axis": "text_presence", "media_type": "image/png"},
                    {"variant_id": "variant_a", "path": "/output/p/thumbnail_variant_a.png", "axis": "text_presence", "media_type": "image/png"},
                    {"variant_id": "variant_b", "path": "/output/p/thumbnail_variant_b.png", "axis": "text_presence", "media_type": "image/png"},
                ]
            },
        },
    )
    spec = ExperimentEngine().build_from_optimization(report=report, project=project)
    assert spec["dimension"] == "thumbnail"
    assert spec["variants"]["variant_a"]["artifact_path"].endswith("thumbnail_variant_a.png")
    assert spec["variants"]["variant_b"]["variant_axis"] == "text_presence"
