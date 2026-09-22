from app.content.strategy import ContentStrategyEngine


def test_strategy_builds_ranked_ideas():
    engine = ContentStrategyEngine()
    ideas = engine.generate(
        channel={"name": "Tech", "niche": "AI technology", "language": "en"},
        memory={"version": 2, "learned_patterns": [{"type": "retention_baseline", "median": 62}]},
        seed_topics=["AI agents"],
        count=5,
        goal="growth",
    )
    assert len(ideas) == 5
    assert ideas[0].composite_score >= ideas[-1].composite_score
    assert ideas[0].hook


def test_strategy_uses_retention_memory_for_hook():
    engine = ContentStrategyEngine()
    ideas = engine.generate(
        channel={"name": "Tech", "niche": "AI", "language": "en"},
        memory={"version": 1, "learned_patterns": [{"type": "retention_baseline", "median": 70}]},
        seed_topics=["AI agents"],
        count=1,
        goal="balanced",
    )
    assert "nobody sees coming" in ideas[0].hook
