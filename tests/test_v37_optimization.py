from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.autonomous_optimization import AutonomousOptimizationService


def _project():
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        channel_id="00000000-0000-0000-0000-000000000002",
        data={
            "content_blueprint": {"format": "case_study"},
            "youtube_video_id": "video-1",
        },
    )


def _channel():
    return SimpleNamespace(
        id="00000000-0000-0000-0000-000000000002",
        organization_id="00000000-0000-0000-0000-000000000003",
    )


def test_retention_selects_blueprint_replan():
    service = AutonomousOptimizationService.__new__(AutonomousOptimizationService)
    ctx = {
        "alert": {"metric": "retention", "delta_pct": -31.0, "severity": "high", "evidence": {}},
        "creative": {"score": 88, "scene_reports": [], "issues": [], "recommendations": []},
        "multimodal": {"score": 90, "conflicts": []},
    }
    plan = service._deterministic_plan(ctx, max_actions=3)
    assert plan["target_scope"] == "blueprint_replan"
    assert plan["status"] == "PROPOSED"
    assert plan["action_plan"]["actions"]
    assert "published_source_immutable" in plan["guardrails"]


def test_ctr_selects_packaging_experiment():
    service = AutonomousOptimizationService.__new__(AutonomousOptimizationService)
    ctx = {
        "alert": {"metric": "ctr", "delta_pct": -25.0, "severity": "medium", "evidence": {}},
        "creative": {"score": 90, "scene_reports": [], "issues": [], "recommendations": []},
        "multimodal": {"score": 92, "conflicts": []},
    }
    plan = service._deterministic_plan(ctx, max_actions=3)
    assert plan["target_scope"] == "packaging_experiment"
    assert {a["dimension"] for a in plan["action_plan"]["actions"]} == {"thumbnail", "title"}


def test_scene_mismatch_selects_scene_reedit():
    service = AutonomousOptimizationService.__new__(AutonomousOptimizationService)
    ctx = {
        "alert": {"metric": "views", "delta_pct": -18.0, "severity": "medium", "evidence": {}},
        "creative": {"score": 75, "scene_reports": [{"scene": 3, "narration_visual_alignment": 0.31, "issues": ["mismatch"]}], "issues": [], "recommendations": []},
        "multimodal": {"score": 80, "conflicts": []},
    }
    plan = service._deterministic_plan(ctx, max_actions=3)
    assert plan["target_scope"] == "scene_reedit"
    assert plan["action_plan"]["actions"][0]["scene"] == 3


def test_normalize_never_allows_unknown_scope():
    service = AutonomousOptimizationService.__new__(AutonomousOptimizationService)
    plan = service._normalize_ai_plan(
        {"target_scope": "delete_channel", "priority": 4, "confidence": -1, "action_plan": {"actions": list(range(20))}},
        {"alert": {}},
        max_actions=2,
    )
    assert plan["target_scope"] == "no_action"
    assert plan["priority"] == 1.0
    assert plan["confidence"] == 0.0
    assert len(plan["action_plan"]["actions"]) == 2


def test_max_actions_validation():
    service = AutonomousOptimizationService.__new__(AutonomousOptimizationService)
    with pytest.raises(ValueError):
        import asyncio
        asyncio.run(service.decide(project=_project(), channel=_channel(), alert=None, max_actions=13))


def test_normalize_blocks_low_confidence():
    service = AutonomousOptimizationService.__new__(AutonomousOptimizationService)
    plan = service._normalize_ai_plan(
        {"target_scope": "scene_reedit", "priority": 0.8, "confidence": 0.1, "action_plan": {"actions": [{"scene": 1}]}},
        {"alert": {}},
        max_actions=2,
    )
    assert plan["status"] == "BLOCKED"
