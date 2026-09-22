from __future__ import annotations
from dataclasses import dataclass
from statistics import mean, median
from typing import Any


@dataclass
class VideoMetricRow:
    video_id: str
    views: float = 0
    watch_time_minutes: float = 0
    avg_view_duration: float = 0
    avg_view_percentage: float = 0
    likes: float = 0
    comments: float = 0
    shares: float = 0
    subscribers_gained: float = 0
    subscribers_lost: float = 0


class ChannelBrainAnalyzer:
    """Deterministic baseline analyzer. It produces explainable hypotheses from stored analytics."""

    def analyze_channel(self, rows: list[VideoMetricRow]) -> dict[str, Any]:
        if not rows:
            return {
                "summary": "No analytics data available yet.",
                "learned_patterns": [],
                "topic_clusters": [],
                "hook_patterns": [],
                "title_patterns": [],
                "pacing_patterns": [],
                "production_notes": [],
            }

        views = [r.views for r in rows]
        retention = [r.avg_view_percentage for r in rows if r.avg_view_percentage > 0]
        sub_gain = [r.subscribers_gained for r in rows]

        patterns: list[dict[str, Any]] = []
        if retention:
            patterns.append({
                "type": "retention_baseline",
                "metric": "averageViewPercentage",
                "median": round(median(retention), 2),
                "mean": round(mean(retention), 2),
            })
        patterns.append({
            "type": "view_baseline",
            "metric": "views",
            "median": round(median(views), 2),
            "mean": round(mean(views), 2),
        })
        patterns.append({
            "type": "subscriber_baseline",
            "metric": "subscribersGained",
            "median": round(median(sub_gain), 2),
        })

        summary = (
            f"Channel baseline built from {len(rows)} video metric rows. "
            f"Median views: {median(views):.0f}."
        )
        if retention:
            summary += f" Median average-view-percentage: {median(retention):.1f}%."

        return {
            "summary": summary,
            "learned_patterns": patterns,
            "topic_clusters": [],
            "hook_patterns": [],
            "title_patterns": [],
            "pacing_patterns": [],
            "production_notes": [],
        }

    def optimize_video(self, row: VideoMetricRow, baseline: dict[str, Any]) -> dict[str, Any]:
        patterns = baseline.get("learned_patterns", [])
        median_views = next((p.get("median", 0) for p in patterns if p.get("type") == "view_baseline"), 0)
        median_retention = next((p.get("median", 0) for p in patterns if p.get("type") == "retention_baseline"), 0)

        actions: list[str] = []
        hypotheses: list[str] = []
        diagnosis: dict[str, Any] = {}

        if median_views:
            diagnosis["views_vs_baseline_pct"] = round((row.views / median_views - 1) * 100, 1)
            if row.views < median_views * 0.75:
                actions.append("Review topic-market fit and packaging before repeating the format.")
                hypotheses.append("The video may have weaker topic demand or packaging than the channel baseline.")

        if median_retention and row.avg_view_percentage:
            diagnosis["retention_vs_baseline_pct"] = round((row.avg_view_percentage / median_retention - 1) * 100, 1)
            if row.avg_view_percentage < median_retention * 0.85:
                actions.append("Shorten the opening and increase visual or narrative changes in the first third.")
                hypotheses.append("Early pacing or expectation mismatch may be reducing retention.")
            elif row.avg_view_percentage > median_retention * 1.15:
                actions.append("Reuse the narrative structure and pacing pattern in related future topics.")
                hypotheses.append("The current structure appears compatible with the audience's viewing behavior.")

        sub_baseline = next((p.get("median", 0) for p in patterns if p.get("type") == "subscriber_baseline"), 0)
        if sub_baseline:
            diagnosis["subscribers_vs_baseline_pct"] = round((row.subscribers_gained / sub_baseline - 1) * 100, 1) if row.subscribers_gained else -100.0
            if row.subscribers_gained > sub_baseline * 1.15:
                diagnosis["subscriber_signal"] = "positive"
            elif row.subscribers_gained < sub_baseline * 0.85:
                diagnosis["subscriber_signal"] = "weak"

        confidence = 0.55
        if median_views and median_retention:
            confidence = 0.72
        return {
            "diagnosis": diagnosis,
            "actions": actions,
            "hypotheses": hypotheses,
            "confidence": confidence,
        }
