from __future__ import annotations

import uuid
from datetime import datetime
from statistics import mean
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContentExperiment, ExperimentObservation, OptimizationReport, AnalyticsSnapshot, VideoProject, Channel


EXPERIMENT_DIMENSIONS = {"title", "thumbnail", "hook", "pacing", "topic_angle"}


class ExperimentEngine:
    """Creates and evaluates observational experiments.

    This engine tracks variants and before/after observations. It does not claim
    YouTube-native A/B exposure control; the platform can import observations from
    analytics or user-entered experiment windows and evaluate them consistently.
    """

    def build_from_optimization(self, *, report: OptimizationReport, project: VideoProject | None) -> dict[str, Any]:
        actions = list(report.actions or [])
        hypotheses = list(report.hypotheses or [])
        action_text = " ".join(actions + hypotheses).lower()
        if "thumbnail" in action_text:
            dimension = "thumbnail"
        elif "title" in action_text or "packaging" in action_text:
            dimension = "title"
        elif "hook" in action_text or "opening" in action_text:
            dimension = "hook"
        elif "pacing" in action_text or "visual" in action_text:
            dimension = "pacing"
        else:
            dimension = "topic_angle"

        base_title = ((project.data or {}).get("title") if project else None) or (project.topic if project else "Current video")
        base_hook = ((project.data or {}).get("hook") if project else None) or "Current opening"
        variants = {
            "control": {"label": "Control", "title": base_title, "hook": base_hook, "notes": "Keep the current packaging/structure."},
            "variant_a": self._variant_a(dimension, base_title, base_hook),
            "variant_b": self._variant_b(dimension, base_title, base_hook),
        }
        if dimension == "thumbnail" and project:
            thumbnail = (project.data or {}).get("thumbnail") or {}
            physical_variants = thumbnail.get("variants") or []
            by_id = {
                str(item.get("variant_id")): item
                for item in physical_variants
                if item.get("variant_id")
            }
            for key, item in by_id.items():
                if key in variants:
                    variants[key] = {
                        **variants[key],
                        "artifact_path": item.get("path"),
                        "artifact_media_type": item.get("media_type"),
                        "variant_axis": item.get("axis"),
                    }
        hypothesis = hypotheses[0] if hypotheses else "A targeted packaging or structure change may improve the observed weak signal."
        return {
            "dimension": dimension,
            "experiment_type": "observational",
            "hypothesis": hypothesis,
            "variants": variants,
            "decision_rule": {
                "primary_metric": "ctr" if dimension in {"title", "thumbnail"} else "average_view_percentage",
                "minimum_observations": 2,
                "note": "Compare normalized metrics across observation windows; do not infer causality from a single snapshot.",
            },
        }

    async def create_from_report(self, db: AsyncSession, *, channel_id: str, report_id: str) -> ContentExperiment:
        report = await db.get(OptimizationReport, uuid.UUID(report_id))
        if not report or str(report.channel_id) != channel_id:
            raise ValueError("Optimization report not found")
        project = await db.get(VideoProject, report.video_project_id) if getattr(report, "video_project_id", None) else None
        spec = self.build_from_optimization(report=report, project=project)
        experiment = ContentExperiment(
            channel_id=uuid.UUID(channel_id),
            video_project_id=project.id if project else None,
            experiment_type=spec["experiment_type"],
            dimension=spec["dimension"],
            hypothesis=spec["hypothesis"],
            variants=spec["variants"],
            decision_rule=spec["decision_rule"],
        )
        db.add(experiment)
        await db.commit()
        await db.refresh(experiment)
        return experiment

    async def create_manual(self, db: AsyncSession, *, channel_id: str, payload: dict[str, Any]) -> ContentExperiment:
        dimension = payload["dimension"]
        if dimension not in EXPERIMENT_DIMENSIONS:
            raise ValueError(f"Unsupported experiment dimension: {dimension}")
        variants = payload.get("variants") or {
            "control": {"label": "Control"},
            "variant_a": {"label": "Variant A"},
        }
        experiment = ContentExperiment(
            channel_id=uuid.UUID(channel_id),
            video_project_id=uuid.UUID(payload["video_project_id"]) if payload.get("video_project_id") else None,
            experiment_type=payload.get("experiment_type", "observational"),
            dimension=dimension,
            hypothesis=payload.get("hypothesis", ""),
            variants=variants,
            decision_rule=payload.get("decision_rule", {"primary_metric": "average_view_percentage"}),
        )
        db.add(experiment)
        await db.commit()
        await db.refresh(experiment)
        return experiment

    async def observe(self, db: AsyncSession, experiment: ContentExperiment, payload: dict[str, Any]) -> ExperimentObservation:
        key = str(payload["variant_key"])
        if key not in (experiment.variants or {}):
            raise ValueError("Unknown experiment variant")
        observed_at = datetime.fromisoformat(payload["observed_at"]) if payload.get("observed_at") else datetime.utcnow()
        obs = ExperimentObservation(
            experiment_id=experiment.id,
            variant_key=key,
            observed_at=observed_at,
            views=int(payload.get("views", 0) or 0),
            impressions=int(payload.get("impressions", 0) or 0),
            ctr=float(payload.get("ctr", 0) or 0),
            average_view_percentage=float(payload.get("average_view_percentage", 0) or 0),
            watch_time_minutes=float(payload.get("watch_time_minutes", 0) or 0),
            subscribers_gained=int(payload.get("subscribers_gained", 0) or 0),
            raw=payload.get("raw") or {},
        )
        db.add(obs)
        if experiment.status == "DRAFT":
            experiment.status = "RUNNING"
            experiment.started_at = datetime.utcnow()
        await db.commit()
        await db.refresh(obs)
        return obs

    async def evaluate(self, db: AsyncSession, experiment_id: str) -> dict[str, Any]:
        experiment = await db.get(ContentExperiment, uuid.UUID(experiment_id))
        if not experiment:
            raise ValueError("Experiment not found")
        q = await db.execute(select(ExperimentObservation).where(ExperimentObservation.experiment_id == experiment.id).order_by(ExperimentObservation.observed_at))
        rows = list(q.scalars().all())
        grouped: dict[str, list[ExperimentObservation]] = {}
        for row in rows:
            grouped.setdefault(row.variant_key, []).append(row)

        primary = (experiment.decision_rule or {}).get("primary_metric", "average_view_percentage")
        minimum = int((experiment.decision_rule or {}).get("minimum_observations", 2))
        summaries: dict[str, Any] = {}
        for key, observations in grouped.items():
            values = [float(getattr(o, primary, 0) or 0) for o in observations]
            summaries[key] = {
                "observations": len(observations),
                "metric": primary,
                "mean": round(mean(values), 4) if values else 0,
                "latest": values[-1] if values else 0,
            }

        ready = [k for k, v in summaries.items() if v["observations"] >= minimum]
        ranking = sorted(ready, key=lambda k: summaries[k]["mean"], reverse=True)
        result = {
            "experiment_id": str(experiment.id),
            "status": experiment.status,
            "primary_metric": primary,
            "variant_summaries": summaries,
            "decision": None,
            "limitations": ["Observational data alone does not prove causality or randomized exposure."],
        }
        if len(ranking) >= 2:
            top, second = ranking[0], ranking[1]
            delta = summaries[top]["mean"] - summaries[second]["mean"]
            result["decision"] = {
                "state": "signal_detected",
                "leading_variant": top,
                "delta_vs_second": round(delta, 4),
            }
        elif len(ranking) == 1:
            result["decision"] = {"state": "insufficient_comparison", "leading_variant": ranking[0]}
        experiment.result = result
        await db.commit()
        return result

    async def close(self, db: AsyncSession, experiment_id: str) -> dict[str, Any]:
        result = await self.evaluate(db, experiment_id)
        experiment = await db.get(ContentExperiment, uuid.UUID(experiment_id))
        experiment.status = "COMPLETED"
        experiment.ended_at = datetime.utcnow()
        await db.commit()
        from app.brain.service import learn_from_experiment
        await learn_from_experiment(db, experiment_id)
        result["status"] = "COMPLETED"
        result["learned_pattern"] = True
        return result

    def _variant_a(self, dimension: str, title: str, hook: str) -> dict[str, Any]:
        if dimension == "title":
            return {"label": "Curiosity packaging", "title": f"The Hidden Problem With {title}", "hook": hook}
        if dimension == "thumbnail":
            return {"label": "Minimal thumbnail", "visual_style": "single_subject_high_contrast", "title": title}
        if dimension == "hook":
            return {"label": "Question hook", "hook": f"What if the assumption behind {title} is wrong?", "title": title}
        if dimension == "pacing":
            return {"label": "Faster pacing", "visual_change_seconds": 3.5, "title": title}
        return {"label": "Case-study angle", "angle": "case-study", "title": title}

    def _variant_b(self, dimension: str, title: str, hook: str) -> dict[str, Any]:
        if dimension == "title":
            return {"label": "Outcome packaging", "title": f"What {title} Really Means", "hook": hook}
        if dimension == "thumbnail":
            return {"label": "Face + text thumbnail", "visual_style": "subject_text_split", "title": title}
        if dimension == "hook":
            return {"label": "Outcome hook", "hook": f"In the next few minutes, you will see exactly why {title} matters.", "title": title}
        if dimension == "pacing":
            return {"label": "Moderate pacing", "visual_change_seconds": 5.0, "title": title}
        return {"label": "Practical angle", "angle": "practical-guide", "title": title}
