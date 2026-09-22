from app.content.intelligence import ContentIntelligenceEngine


def test_blueprint_uses_case_study_for_case_angle():
    engine = ContentIntelligenceEngine()
    bp = engine.build_blueprint(
        channel={"name": "Tech", "niche": "AI", "language": "en"},
        memory={},
        idea={"topic": "AI layoffs case study", "title": "What AI Layoffs Teach Us", "angle": "case-study breakdown"},
        goal="balanced",
    )
    assert bp.format == "case_study"
    assert bp.hook_pattern == "story"
    assert "turning_point" in bp.narrative_structure


def test_blueprint_consumes_learned_format_and_pacing_signals():
    engine = ContentIntelligenceEngine()
    memory = {
        "learned_patterns": [{"type": "format_signal", "format": "tutorial"}],
        "pacing_patterns": [{"median_duration_minutes": 13, "visual_change_seconds": 3.2}],
        "hook_patterns": [{"pattern": "contrarian"}],
        "topic_clusters": [{"topic": "AI"}],
    }
    bp = engine.build_blueprint(
        channel={"name": "Tech", "niche": "AI", "language": "en"},
        memory=memory,
        idea={"topic": "AI tooling", "title": "The Problem With AI Tooling", "angle": "contrarian explanation"},
        goal="authority",
    )
    assert bp.format == "tutorial"
    assert bp.hook_pattern == "contrarian"
    assert bp.target_duration_minutes == 13
    assert bp.visual_change_seconds == 3.2
    assert bp.confidence >= 0.7


def test_blueprint_contains_experiment_spec():
    engine = ContentIntelligenceEngine()
    bp = engine.build_blueprint(
        channel={"name": "Tech", "niche": "AI", "language": "en"},
        memory={},
        idea={"topic": "AI agents", "title": "AI Agents — What Happens Next?", "angle": "future impact"},
        goal="growth",
    )
    assert bp.experiment_spec["dimension"] in {"thumbnail", "title", "hook", "pacing", "topic_angle"}
    assert bp.experiment_spec["primary_metric"] in {"ctr", "average_view_percentage"}
