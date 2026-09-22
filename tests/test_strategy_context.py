from app.content.strategy import ContentStrategyEngine


def test_goal_changes_composite_scoring():
    engine = ContentStrategyEngine()
    common = {
        "channel": {"name": "Tech", "niche": "AI", "language": "en"},
        "memory": {},
        "seed_topics": ["AI agents", "future of software"],
        "count": 2,
    }
    growth = engine.generate(**common, goal="growth")
    authority = engine.generate(**common, goal="authority")
    assert [x.composite_score for x in growth] != [x.composite_score for x in authority]
