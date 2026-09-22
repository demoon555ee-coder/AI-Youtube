from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from statistics import median
from typing import Any


@dataclass(frozen=True)
class OpportunitySignal:
    topic: str
    score: float
    demand_signal: float
    competition_signal: float
    freshness_signal: float
    gap_signal: float
    channel_fit: float
    rationale: dict[str, Any]
    source_node_ids: list[str]


class OpportunityDetector:
    """Heuristic opportunity detection, explicitly treated as a signal rather than prediction."""

    def detect(self, *, channel: dict[str, Any], query: str, results: list[dict[str, Any]], node_ids: list[str]) -> list[OpportunitySignal]:
        if not results:
            return []
        niche_tokens = self._tokens(str(channel.get("niche") or ""))
        title_tokens = [self._tokens(str(x.get("title") or "")) for x in results]
        unique_channels = {str(x.get("channel_id")) for x in results if x.get("channel_id")}
        channel_count = max(1, len(unique_channels))
        max_views = max((int(x.get("views") or 0) for x in results), default=0)
        avg_views = sum(int(x.get("views") or 0) for x in results) / max(1, len(results))

        demand = self._norm_log(max_views, cap=1e9) * 0.65 + self._norm_log(avg_views, cap=1e8) * 0.35
        competition = min(1.0, channel_count / max(1.0, len(results) * 0.8))
        freshness_values = [self._freshness(str(x.get("published_at") or "")) for x in results]
        freshness = sum(freshness_values) / max(1, len(freshness_values))
        fit_values = [self._jaccard(niche_tokens, tokens) for tokens in title_tokens]
        fit = min(1.0, 0.45 + (sum(fit_values) / max(1, len(fit_values))) * 0.7)

        format_tokens = {"how": 0, "why": 0, "guide": 0, "review": 0, "case": 0, "comparison": 0}
        for result in results:
            text = str(result.get("title") or "").lower()
            for key in format_tokens:
                if key in text:
                    format_tokens[key] += 1
        gap_types = [key for key, count in format_tokens.items() if count <= max(1, len(results) // 8)]
        gap_signal = min(1.0, 0.45 + 0.08 * len(gap_types))

        score = (
            demand * 0.30
            + (1.0 - competition) * 0.20
            + freshness * 0.20
            + gap_signal * 0.15
            + fit * 0.15
        )
        top = max(results, key=lambda x: int(x.get("views") or 0))
        topic = self._topic_from_query(query, results)
        rationale = {
            "signal_method": "heuristic",
            "note": "Signals are derived from retrieved public metadata and should not be treated as causal or guaranteed outcomes.",
            "top_result": {"title": top.get("title"), "views": int(top.get("views") or 0), "channel_title": top.get("channel_title")},
            "unique_competing_channels": channel_count,
            "low_frequency_formats": gap_types,
            "sample_size": len(results),
        }
        return [OpportunitySignal(
            topic=topic,
            score=round(max(0.0, min(1.0, score)), 4),
            demand_signal=round(demand, 4),
            competition_signal=round(competition, 4),
            freshness_signal=round(freshness, 4),
            gap_signal=round(gap_signal, 4),
            channel_fit=round(fit, 4),
            rationale=rationale,
            source_node_ids=node_ids,
        )]

    def _topic_from_query(self, query: str, results: list[dict[str, Any]]) -> str:
        if query.strip():
            return query.strip()
        words = re.findall(r"[\w'-]+", str((results[0] if results else {}).get("title") or ""))
        return " ".join(words[:10]) or "Untitled research topic"

    def _freshness(self, published_at: str) -> float:
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            age_days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
            return math.exp(-age_days / 30.0)
        except (ValueError, TypeError):
            return 0.25

    def _norm_log(self, value: int | float, *, cap: float) -> float:
        if value <= 0:
            return 0.0
        return min(1.0, math.log1p(value) / math.log1p(cap))

    def _tokens(self, value: str) -> set[str]:
        return {x for x in re.findall(r"[a-zA-Z0-9а-яА-Я]{4,}", value.lower()) if x not in {"with", "from", "this", "that", "about", "your", "what"}}

    def _jaccard(self, a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / max(1, len(a | b))
