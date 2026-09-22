from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    AutonomousOptimizationDecision,
    Channel,
    CreativeAnalysis,
    PerformanceAlert,
    ProductionMultimodalGraph,
    VideoProject,
)
from app.providers.factory import get_llm


TARGET_SCOPES = {"scene_reedit", "packaging_experiment", "blueprint_replan", "full_rebuild", "no_action"}


class AutonomousOptimizationService:
    """Turns post-publish and multimodal signals into one bounded next action.

    The service deliberately separates observation from execution. A decision never mutates a
    published project; execution is delegated to existing evolution/experiment workflows.
    """

    def __init__(self, db: AsyncSession, llm_provider=None, llm_config: dict | None = None):
        self.db = db
        self.llm = None
        if settings.optimization_ai_enabled:
            self.llm = llm_provider or get_llm(llm_config.get("provider") if llm_config else None, (llm_config or {}).get("config") if llm_config else None)

    async def decide(self, *, project: VideoProject, channel: Channel, alert: PerformanceAlert | None = None, max_actions: int = 3) -> AutonomousOptimizationDecision:
        if max_actions < 0 or max_actions > 12:
            raise ValueError("max_actions must be between 0 and 12")

        existing = None
        if alert is not None:
            existing = await self.db.scalar(
                select(AutonomousOptimizationDecision).where(
                    AutonomousOptimizationDecision.organization_id == channel.organization_id,
                    AutonomousOptimizationDecision.source_alert_id == alert.id,
                )
            )
            if existing:
                return existing

        creative = await self.db.scalar(
            select(CreativeAnalysis).where(CreativeAnalysis.project_id == project.id).order_by(CreativeAnalysis.created_at.desc())
        )
        graph = await self.db.scalar(
            select(ProductionMultimodalGraph).where(ProductionMultimodalGraph.project_id == project.id).order_by(ProductionMultimodalGraph.created_at.desc())
        )

        context = self._context(project, alert, creative, graph)
        if self.llm is not None:
            try:
                raw = await self.llm.generate_json(
                    system=self._system_prompt(),
                    user=json.dumps(context, ensure_ascii=False),
                )
                plan = self._normalize_ai_plan(raw, context, max_actions=max_actions)
            except Exception:
                plan = self._deterministic_plan(context, max_actions=max_actions)
        else:
            plan = self._deterministic_plan(context, max_actions=max_actions)

        row = AutonomousOptimizationDecision(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            project_id=project.id,
            source_alert_id=alert.id if alert else None,
            target_scope=plan["target_scope"],
            priority=plan["priority"],
            confidence=plan["confidence"],
            status=plan["status"],
            hypothesis=plan["hypothesis"],
            evidence=plan["evidence"],
            action_plan=plan["action_plan"],
            guardrails=plan["guardrails"],
        )
        self.db.add(row)
        await self.db.flush()
        return row

    def _context(self, project, alert, creative, graph) -> dict[str, Any]:
        data = project.data or {}
        return {
            "project_id": str(project.id),
            "channel_id": str(project.channel_id),
            "alert": {
                "type": alert.alert_type if alert else None,
                "metric": alert.metric if alert else None,
                "delta_pct": alert.delta_pct if alert else None,
                "severity": alert.severity if alert else None,
                "evidence": alert.evidence if alert else {},
            },
            "creative": {
                "score": creative.score if creative else None,
                "issues": creative.issues if creative else [],
                "recommendations": creative.recommendations if creative else [],
                "scene_reports": creative.scene_reports if creative else [],
                "audio": creative.audio_analysis if creative else {},
                "visual": creative.visual_analysis if creative else {},
            },
            "multimodal": {
                "score": graph.score if graph else None,
                "risk_level": graph.risk_level if graph else None,
                "conflicts": graph.conflicts if graph else [],
                "recommendations": graph.recommendations if graph else [],
                "signals": graph.signals if graph else {},
                "nodes": graph.nodes if graph else [],
            },
            "content_blueprint": data.get("content_blueprint") or data.get("blueprint") or {},
            "published": bool(data.get("publication") or data.get("youtube_video_id")),
        }

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an autonomous YouTube optimization planner. Choose exactly one target_scope from "
            "scene_reedit, packaging_experiment, blueprint_replan, full_rebuild, no_action. "
            "Use observed evidence only; never claim causality from correlation. Never modify an existing "
            "published artifact in place. Prefer the smallest safe intervention. Return JSON with: "
            "target_scope, priority, confidence, status, hypothesis, evidence, action_plan, guardrails."
        )

    def _normalize_ai_plan(self, raw: dict[str, Any], context: dict[str, Any], *, max_actions: int) -> dict[str, Any]:
        target = str(raw.get("target_scope") or "no_action")
        if target not in TARGET_SCOPES:
            target = "no_action"
        try:
            priority = max(0.0, min(1.0, float(raw.get("priority", 0.0))))
        except (TypeError, ValueError):
            priority = 0.0
        try:
            confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        status = str(raw.get("status") or ("PROPOSED" if target != "no_action" else "NO_ACTION"))
        allowed_status = {"PROPOSED", "APPROVED", "NO_ACTION", "BLOCKED"}
        if status not in allowed_status:
            status = "PROPOSED"
        if target != "no_action" and confidence < settings.optimization_min_confidence:
            status = "BLOCKED"
        action_plan = raw.get("action_plan") if isinstance(raw.get("action_plan"), dict) else {}
        actions = action_plan.get("actions") if isinstance(action_plan.get("actions"), list) else []
        action_plan["actions"] = actions[:max_actions]
        guardrails = raw.get("guardrails") if isinstance(raw.get("guardrails"), list) else []
        base_guardrails = {
            "published_source_immutable": True,
            "requires_quality_gate": True,
            "requires_content_write_permission": True,
        }
        merged_guardrails = list(dict.fromkeys([*base_guardrails.keys(), *[str(x) for x in guardrails]]))
        return {
            "target_scope": target,
            "priority": priority,
            "confidence": confidence,
            "status": status,
            "hypothesis": str(raw.get("hypothesis") or ""),
            "evidence": raw.get("evidence") if isinstance(raw.get("evidence"), dict) else context.get("alert", {}),
            "action_plan": action_plan,
            "guardrails": merged_guardrails,
        }

    def _deterministic_plan(self, context: dict[str, Any], *, max_actions: int) -> dict[str, Any]:
        alert = context.get("alert") or {}
        creative = context.get("creative") or {}
        multimodal = context.get("multimodal") or {}
        metric = str(alert.get("metric") or "").lower()
        delta = float(alert.get("delta_pct") or 0.0)
        scene_reports = creative.get("scene_reports") or []
        mismatches = [x for x in scene_reports if float(x.get("narration_visual_alignment", 1.0) or 0.0) < 0.55]
        mm_conflicts = multimodal.get("conflicts") or []
        actions: list[dict[str, Any]] = []

        if mismatches:
            for row in mismatches[:max_actions]:
                actions.append({
                    "scene": row.get("scene"),
                    "action": "replace_visual",
                    "reason": row.get("issues") or ["narration_visual_mismatch"],
                    "confidence": 0.74,
                })
            target = "scene_reedit"
            priority = min(1.0, 0.65 + 0.05 * len(mismatches))
            hypothesis = "Observed scene-level visual mismatch may be contributing to weak creative quality; test a targeted visual replacement."
        elif metric in {"ctr", "impression_ctr"}:
            actions = [{"dimension": "thumbnail", "action": "test_variant"}, {"dimension": "title", "action": "test_variant"}][:max_actions]
            target = "packaging_experiment"
            priority = min(1.0, 0.65 + abs(delta) / 100)
            hypothesis = "Packaging metrics are materially below the observed baseline; test title/thumbnail variants rather than re-rendering the video."
        elif metric in {"retention", "average_view_percentage", "opening"}:
            actions = [{"action": "replan_hook", "scope": "opening_third"}, {"action": "increase_visual_pacing", "scope": "opening_third"}][:max_actions]
            target = "blueprint_replan"
            priority = min(1.0, 0.62 + abs(delta) / 110)
            hypothesis = "Retention signal is below baseline; adjust the next production blueprint before full re-render."
        elif metric == "views":
            actions = [{"action": "refresh_topic_angle"}, {"action": "review_packaging"}][:max_actions]
            target = "blueprint_replan"
            priority = min(1.0, 0.55 + abs(delta) / 130)
            hypothesis = "View volume is below baseline; investigate topic angle and packaging before rebuilding the whole video."
        elif mm_conflicts or float(multimodal.get("score") or 100) < 60 or float(creative.get("score") or 100) < 60:
            target = "scene_reedit"
            priority = 0.58
            hypothesis = "Multimodal production evidence shows localized quality conflicts; prefer bounded scene re-edit."
        else:
            target = "no_action"
            priority = 0.0
            hypothesis = "No sufficiently strong, actionable signal is present."

        confidence = 0.82 if target != "no_action" else 0.65
        return {
            "target_scope": target,
            "priority": round(priority, 4),
            "confidence": confidence,
            "status": "PROPOSED" if target != "no_action" else "NO_ACTION",
            "hypothesis": hypothesis,
            "evidence": {"alert": alert, "creative_score": creative.get("score"), "multimodal_score": multimodal.get("score"), "multimodal_conflicts": mm_conflicts},
            "action_plan": {"actions": actions, "execution": "delegate_to_existing_evolution_or_experiment_workflow"},
            "guardrails": ["published_source_immutable", "requires_quality_gate", "requires_content_write_permission", "bounded_intervention"],
        }


def serialize_decision(row: AutonomousOptimizationDecision) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id) if row.organization_id else None,
        "channel_id": str(row.channel_id),
        "project_id": str(row.project_id),
        "source_alert_id": str(row.source_alert_id) if row.source_alert_id else None,
        "target_scope": row.target_scope,
        "priority": row.priority,
        "confidence": row.confidence,
        "status": row.status,
        "hypothesis": row.hypothesis,
        "evidence": row.evidence,
        "action_plan": row.action_plan,
        "guardrails": row.guardrails,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
