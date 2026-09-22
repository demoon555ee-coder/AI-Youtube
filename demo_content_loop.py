"""Offline demonstration of the v0.7 Channel Brain -> Content Strategy loop."""
from app.content.strategy import ContentStrategyEngine


def main() -> None:
    engine = ContentStrategyEngine()
    channel = {"name": "AI Lab", "niche": "AI technology", "language": "en"}
    memory = {
        "version": 7,
        "learned_patterns": [
            {"type": "view_baseline", "median": 42000},
            {"type": "retention_baseline", "median": 61.5},
        ],
        "topic_clusters": ["AI agents", "automation", "software engineering"],
    }
    strategy = engine.build_strategy(channel=channel, memory=memory, goal="growth")
    ideas = engine.generate(
        channel=channel,
        memory=memory,
        seed_topics=["AI agents", "automation"],
        count=5,
        goal="growth",
    )
    print("STRATEGY")
    print(strategy)
    print("\nTOP IDEAS")
    for index, idea in enumerate(ideas, start=1):
        print(f"{index}. {idea.title} | score={idea.composite_score} | hook={idea.hook}")


if __name__ == "__main__":
    main()
