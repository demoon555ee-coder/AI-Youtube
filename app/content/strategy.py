from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass
class IdeaCandidate:
    topic: str
    title: str
    hook: str
    angle: str
    duration_minutes: int
    demand_signal: float
    competition_signal: float
    channel_fit: float
    novelty: float
    production_cost: float
    composite_score: float
    rationale: dict[str, Any]


class ContentStrategyEngine:
    """Explainable strategy engine. Scores candidates using channel memory and user goal."""

    GOAL_WEIGHTS = {
        "growth": {"demand": 0.30, "fit": 0.25, "novelty": 0.18, "competition": 0.17, "cost": 0.10},
        "authority": {"demand": 0.16, "fit": 0.34, "novelty": 0.24, "competition": 0.14, "cost": 0.12},
        "monetization": {"demand": 0.28, "fit": 0.25, "novelty": 0.12, "competition": 0.15, "cost": 0.20},
        "balanced": {"demand": 0.24, "fit": 0.26, "novelty": 0.18, "competition": 0.16, "cost": 0.16},
    }

    def generate(self, *, channel: dict[str, Any], memory: dict[str, Any], seed_topics: list[str], count: int, goal: str) -> list[IdeaCandidate]:
        goal = goal if goal in self.GOAL_WEIGHTS else "balanced"
        seeds = seed_topics or self._fallback_topics(channel, memory)
        candidates: list[IdeaCandidate] = []

        patterns = memory.get("learned_patterns") or []
        baseline = {p.get("type"): p for p in patterns if isinstance(p, dict)}
        retention_median = float((baseline.get("retention_baseline") or {}).get("median") or 0)

        for index in range(max(count * 2, count)):
            seed = seeds[index % len(seeds)]
            variant = index // len(seeds)
            topic = self._variant_topic(seed, variant)
            key = int(sha256(topic.encode("utf-8")).hexdigest()[:8], 16)
            demand = 0.55 + (key % 31) / 100
            competition = 0.35 + ((key // 31) % 36) / 100
            fit = self._channel_fit(topic, channel, memory)
            novelty = 0.55 + ((key // 97) % 36) / 100
            production_cost = 0.30 + ((key // 193) % 46) / 100
            weights = self.GOAL_WEIGHTS[goal]
            score = (
                demand * weights["demand"]
                + fit * weights["fit"]
                + novelty * weights["novelty"]
                + (1 - competition) * weights["competition"]
                + (1 - production_cost) * weights["cost"]
            )
            angle = self._angle_for(topic, variant)
            title = self._title_for(topic, angle, variant)
            hook = self._hook_for(topic, angle, retention_median)
            candidates.append(IdeaCandidate(
                topic=topic,
                title=title,
                hook=hook,
                angle=angle,
                duration_minutes=8 + (key % 5),
                demand_signal=round(demand, 3),
                competition_signal=round(competition, 3),
                channel_fit=round(fit, 3),
                novelty=round(novelty, 3),
                production_cost=round(production_cost, 3),
                composite_score=round(score, 3),
                rationale={
                    "goal": goal,
                    "channel_fit_reason": "Matches the configured niche/audience profile.",
                    "retention_baseline_used": retention_median > 0,
                },
            ))

        candidates.sort(key=lambda x: x.composite_score, reverse=True)
        return candidates[:count]

    def build_strategy(self, *, channel: dict[str, Any], memory: dict[str, Any], goal: str) -> dict[str, Any]:
        patterns = memory.get("learned_patterns") or []
        retention = next((p for p in patterns if p.get("type") == "retention_baseline"), None)
        views = next((p for p in patterns if p.get("type") == "view_baseline"), None)
        return {
            "goal": goal,
            "channel": {"name": channel.get("name"), "niche": channel.get("niche"), "language": channel.get("language")},
            "baseline": {
                "median_views": (views or {}).get("median"),
                "median_average_view_percentage": (retention or {}).get("median"),
            },
            "generation_rules": [
                "Prefer topics aligned with the channel niche.",
                "Use learned retention/pacing signals when available.",
                "Preserve novelty without drifting too far from the established audience.",
                "Keep production cost proportional to the selected content goal.",
            ],
            "memory_version": memory.get("version", 0),
        }

    def _fallback_topics(self, channel: dict[str, Any], memory: dict[str, Any]) -> list[str]:
        niche = channel.get("niche") or "the channel niche"
        clusters = memory.get("topic_clusters") or []
        topics = [str(x.get("topic") or x) for x in clusters if x]
        return topics[:8] or [f"The future of {niche}", f"Biggest mistakes in {niche}", f"What everyone gets wrong about {niche}"]

    def _variant_topic(self, seed: str, variant: int) -> str:
        variants = [seed, f"{seed}: what happens next", f"{seed}: the hidden problem", f"{seed}: explained with real examples"]
        return variants[min(variant, len(variants) - 1)]

    def _channel_fit(self, topic: str, channel: dict[str, Any], memory: dict[str, Any]) -> float:
        niche = (channel.get("niche") or "").lower()
        hit = 0.12 if niche and any(token in topic.lower() for token in niche.split()[:3] if len(token) > 3) else 0
        learned = memory.get("topic_clusters") or []
        cluster_bonus = 0.12 if learned else 0
        return min(0.96, 0.67 + hit + cluster_bonus)

    def _angle_for(self, topic: str, variant: int) -> str:
        return ["future impact", "contrarian explanation", "case-study breakdown", "practical guide"][variant % 4]

    def _title_for(self, topic: str, angle: str, variant: int) -> str:
        if angle == "contrarian explanation":
            return f"The Problem With {topic}"
        if angle == "case-study breakdown":
            return f"What {topic} Teaches Us"
        if angle == "practical guide":
            return f"{topic}: A Practical Guide"
        return f"{topic} — What Happens Next?"

    def _hook_for(self, topic: str, angle: str, retention_median: float) -> str:
        base = f"Most people think they understand {topic}."
        if angle == "contrarian explanation":
            base = f"The obvious answer to {topic} is probably wrong."
        elif angle == "case-study breakdown":
            base = f"One real example reveals what {topic} actually means."
        if retention_median >= 60:
            return base + " Here is the part nobody sees coming."
        return base + " In the next few minutes, we will break down why."
