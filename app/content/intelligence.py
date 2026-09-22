from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass
class ContentBlueprintSpec:
    format: str
    hook_pattern: str
    target_duration_minutes: int
    visual_change_seconds: float
    narrative_structure: list[str]
    packaging: dict[str, Any]
    experiment_spec: dict[str, Any]
    reasoning: dict[str, Any]
    confidence: float


class ContentIntelligenceEngine:
    """Deterministic, explainable planner for channel-specific content decisions."""

    FORMATS = ("explainer", "case_study", "tutorial", "documentary", "comparison", "listicle")
    HOOKS = ("question", "contrarian", "outcome", "story", "surprising_fact")

    def build_blueprint(
        self,
        *,
        channel: dict[str, Any],
        memory: dict[str, Any],
        idea: dict[str, Any],
        goal: str = "balanced",
    ) -> ContentBlueprintSpec:
        topic = str(idea.get("topic") or "").strip()
        angle = str(idea.get("angle") or "future impact").lower()
        seed = int(sha256((channel.get("name", "") + "|" + topic + "|" + goal).encode("utf-8")).hexdigest()[:8], 16)

        format_name = self._choose_format(topic, angle, seed, memory)
        hook = self._choose_hook(angle, memory, seed)
        duration = self._choose_duration(goal, memory, seed)
        pacing = self._choose_pacing(memory, seed)
        structure = self._structure(format_name)
        packaging = self._packaging(idea, hook, format_name)
        experiment = self._experiment(idea, hook, format_name, memory)
        evidence = self._evidence(memory, hook, format_name)
        confidence = self._confidence(memory, evidence)

        return ContentBlueprintSpec(
            format=format_name,
            hook_pattern=hook,
            target_duration_minutes=duration,
            visual_change_seconds=pacing,
            narrative_structure=structure,
            packaging=packaging,
            experiment_spec=experiment,
            reasoning={
                "goal": goal,
                "channel_fit": channel.get("niche"),
                "angle_used": angle,
                "evidence": evidence,
                "method": "rule_based_channel_intelligence_v1",
            },
            confidence=round(confidence, 3),
        )

    def _choose_format(self, topic: str, angle: str, seed: int, memory: dict[str, Any]) -> str:
        learned = memory.get("learned_patterns") or []
        prior_formats = [str(p.get("format")) for p in learned if isinstance(p, dict) and p.get("type") == "format_signal"]
        if prior_formats:
            counts = {f: prior_formats.count(f) for f in set(prior_formats) if f in self.FORMATS}
            if counts:
                return sorted(counts, key=lambda k: (-counts[k], self.FORMATS.index(k)))[0]
        if "guide" in angle or "practical" in angle or "how" in topic.lower():
            return "tutorial"
        if "case" in angle or "example" in topic.lower():
            return "case_study"
        if "comparison" in topic.lower() or " vs " in topic.lower():
            return "comparison"
        if "hidden" in angle or "contrarian" in angle:
            return "documentary"
        return self.FORMATS[seed % len(self.FORMATS)]

    def _choose_hook(self, angle: str, memory: dict[str, Any], seed: int) -> str:
        hook_patterns = memory.get("hook_patterns") or []
        for p in hook_patterns:
            if isinstance(p, dict) and p.get("pattern") in self.HOOKS:
                return str(p["pattern"])
        if "contrarian" in angle:
            return "contrarian"
        if "case" in angle:
            return "story"
        if "practical" in angle:
            return "outcome"
        return self.HOOKS[seed % len(self.HOOKS)]

    def _choose_duration(self, goal: str, memory: dict[str, Any], seed: int) -> int:
        pacing = memory.get("pacing_patterns") or []
        durations = [int(p.get("median_duration_minutes")) for p in pacing if isinstance(p, dict) and p.get("median_duration_minutes")]
        if durations:
            return max(6, min(20, int(round(sum(durations) / len(durations)))))
        defaults = {"growth": 9, "authority": 12, "monetization": 10, "balanced": 10}
        return defaults.get(goal, 10) + (seed % 2)

    def _choose_pacing(self, memory: dict[str, Any], seed: int) -> float:
        pacing = memory.get("pacing_patterns") or []
        values = [float(p.get("visual_change_seconds")) for p in pacing if isinstance(p, dict) and p.get("visual_change_seconds")]
        if values:
            return round(max(2.5, min(8.0, sum(values) / len(values))), 1)
        return round(3.5 + (seed % 18) / 10, 1)

    def _structure(self, format_name: str) -> list[str]:
        templates = {
            "explainer": ["hook", "promise", "context", "mechanism", "examples", "implications", "takeaway"],
            "case_study": ["hook", "setup", "timeline", "turning_point", "lessons", "takeaway"],
            "tutorial": ["hook", "outcome", "requirements", "steps", "mistakes", "checklist", "cta"],
            "documentary": ["hook", "mystery", "context", "evidence", "reveal", "implications", "ending"],
            "comparison": ["hook", "criteria", "option_a", "option_b", "tradeoffs", "decision_framework", "takeaway"],
            "listicle": ["hook", "criteria", "item_1", "item_2", "item_3", "surprise", "takeaway"],
        }
        return templates[format_name]

    def _packaging(self, idea: dict[str, Any], hook: str, format_name: str) -> dict[str, Any]:
        title = idea.get("title") or idea.get("topic") or "Untitled"
        return {
            "title": title,
            "title_formula": self._title_formula(format_name),
            "thumbnail_direction": {
                "style": "single_focal_subject",
                "text_max_words": 4,
                "composition": "subject_left_text_right",
            },
            "hook": hook,
        }

    def _experiment(self, idea: dict[str, Any], hook: str, format_name: str, memory: dict[str, Any]) -> dict[str, Any]:
        title = idea.get("title") or idea.get("topic") or "Current video"
        signals = [p for p in (memory.get("learned_patterns") or []) if isinstance(p, dict) and p.get("type") == "experiment_signal"]
        recent_dimension = signals[-1].get("dimension") if signals else None
        dimension = recent_dimension if recent_dimension in {"title", "thumbnail", "hook", "pacing", "topic_angle"} else "thumbnail"
        return {
            "dimension": dimension,
            "hypothesis": f"A {dimension} variation should be tested against the control for {title}.",
            "control": {"label": "Current strategy"},
            "variant": {
                "label": "AI alternative",
                "format": format_name,
                "hook_pattern": hook,
            },
            "primary_metric": "ctr" if dimension in {"title", "thumbnail"} else "average_view_percentage",
            "minimum_observations": 2,
        }

    def _title_formula(self, format_name: str) -> str:
        return {
            "explainer": "Topic + unresolved outcome",
            "case_study": "Case + lesson",
            "tutorial": "Outcome + practical guide",
            "documentary": "Mystery + reveal",
            "comparison": "A vs B + decision criterion",
            "listicle": "Curated items + unexpected takeaway",
        }[format_name]

    def _evidence(self, memory: dict[str, Any], hook: str, format_name: str) -> list[str]:
        evidence = []
        if memory.get("learned_patterns"):
            evidence.append("Channel Brain contains learned patterns from historical analytics/experiments.")
        if memory.get("retention_baseline") or any(isinstance(p, dict) and p.get("type") == "retention_baseline" for p in (memory.get("learned_patterns") or [])):
            evidence.append("Retention baseline is available and can inform pacing/duration decisions.")
        if memory.get("hook_patterns"):
            evidence.append(f"Hook library contains prior patterns; selected pattern: {hook}.")
        if memory.get("pacing_patterns"):
            evidence.append(f"Pacing library contains prior observations; selected format: {format_name}.")
        if not evidence:
            evidence.append("No channel-specific learning signal yet; defaults are based on the requested goal and concept angle.")
        return evidence

    def _confidence(self, memory: dict[str, Any], evidence: list[str]) -> float:
        base = 0.45
        if memory.get("learned_patterns"):
            base += 0.12
        if memory.get("hook_patterns"):
            base += 0.10
        if memory.get("pacing_patterns"):
            base += 0.10
        if memory.get("topic_clusters"):
            base += 0.08
        return min(0.9, base + min(0.1, len(evidence) * 0.02))
