from __future__ import annotations

import json
from typing import Any

from app.providers import get_llm


VALID_ACTIONS = {
    "replace_visual",
    "tighten",
    "extend",
    "text_overlay",
    "audio_mix",
    "transition",
    "keep",
    "manual_review",
}


class CreativeDecisionError(ValueError):
    pass


class CreativeDirectorService:
    """Turns scene-level creative evidence into a bounded, executable edit plan.

    The deterministic mode is intentionally conservative. Optional LLM planning is
    normalized through the same schema so it cannot invent unsupported operations.
    """

    def __init__(self, *, llm_provider: str | None = None, llm_config: dict | None = None):
        self.llm = get_llm(llm_provider, llm_config or {})

    async def build_plan(
        self,
        *,
        project: Any,
        analysis: dict[str, Any],
        blueprint: dict[str, Any] | None = None,
        max_changes: int = 3,
    ) -> dict[str, Any]:
        scenes = analysis.get("scene_reports") or []
        max_changes = max(0, min(int(max_changes), 12))
        if not scenes:
            return self._empty_plan(project, "No scene evidence available")

        if getattr(self.llm, "name", "") == "mock":
            raw = self._deterministic(scenes, max_changes=max_changes)
        else:
            prompt = self._prompt(project, analysis, blueprint, max_changes)
            raw = await self.llm.generate_json(
                system=(
                    "You are a conservative video post-production director. Return JSON only. "
                    "Choose at most max_changes scene interventions. Valid actions are: "
                    "replace_visual, tighten, extend, text_overlay, audio_mix, transition, keep, manual_review. "
                    "Only choose interventions supported by evidence. Each selected scene must include scene, action, "
                    "reason, priority, confidence, and parameters. Never invent scene numbers. "
                    "Prefer replace_visual for visual mismatch; tighten for repetitive/slow scenes; "
                    "text_overlay only when a concrete on-screen clarification is warranted; manual_review for unsupported changes."
                ),
                user=prompt,
            )
        plan = self._normalize(raw, scenes, max_changes=max_changes)
        plan["source_project_id"] = str(getattr(project, "id", ""))
        plan["status"] = "READY" if plan["changes"] else "NO_CHANGE"
        plan["execution"] = self._execution_summary(plan["changes"])
        return plan

    def _prompt(self, project, analysis, blueprint, max_changes: int) -> str:
        return json.dumps(
            {
                "project_id": str(getattr(project, "id", "")),
                "max_changes": max_changes,
                "blueprint": blueprint or {},
                "analysis": {
                    "score": analysis.get("score"),
                    "issues": analysis.get("issues", []),
                    "recommendations": analysis.get("recommendations", []),
                    "scene_reports": analysis.get("scene_reports", []),
                    "audio_analysis": analysis.get("audio_analysis", {}),
                    "visual_analysis": analysis.get("visual_analysis", {}),
                },
            },
            ensure_ascii=False,
        )

    def _deterministic(self, scenes: list[dict], *, max_changes: int) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for row in scenes:
            issues = [str(x) for x in (row.get("issues") or [])]
            recs = [str(x) for x in (row.get("recommendations") or [])]
            alignment = float(row.get("narration_visual_alignment", 1.0) or 0.0)
            relevance = float(row.get("relevance_score", 1.0) or 0.0)
            clarity = float(row.get("clarity_score", 1.0) or 0.0)
            signal = max(0.0, min(1.0, (1 - alignment) * 0.55 + (1 - relevance) * 0.25 + (1 - clarity) * 0.20))
            joined = " ".join(issues + recs).lower()
            if alignment < 0.55:
                action = "replace_visual"
                parameters = {"prompt": "Create a clearer visual that directly supports the narration."}
            elif "repet" in joined or "tight" in joined or "slow" in joined:
                action = "tighten"
                parameters = {"duration_multiplier": 0.82}
            elif clarity < 0.65:
                action = "text_overlay"
                parameters = {"text": "Clarify the key visual claim onscreen."}
            elif issues:
                action = "manual_review"
                parameters = {"reason": "Issue detected but no safe automatic edit mapping exists."}
            else:
                action = "keep"
                parameters = {}
            candidates.append({
                "scene": int(row.get("scene", 0)),
                "action": action,
                "reason": issues or ["weak creative signal"],
                "priority": round(signal, 4),
                "confidence": round(max(0.2, min(0.98, 0.55 + signal * 0.4)), 4),
                "parameters": parameters,
            })
        candidates.sort(key=lambda x: (-x["priority"], x["scene"]))
        changes = [x for x in candidates if x["action"] != "keep"][:max_changes]
        return {"changes": changes}

    def _normalize(self, raw: dict[str, Any], scenes: list[dict], *, max_changes: int) -> dict[str, Any]:
        known = {int(x.get("scene", 0)) for x in scenes}
        raw_changes = raw.get("changes") if isinstance(raw, dict) else []
        if not isinstance(raw_changes, list):
            raw_changes = []
        out: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in raw_changes:
            if not isinstance(item, dict):
                continue
            try:
                scene_no = int(item.get("scene"))
            except (TypeError, ValueError):
                continue
            if scene_no not in known or scene_no in seen:
                continue
            action = str(item.get("action") or "manual_review")
            if action not in VALID_ACTIONS:
                action = "manual_review"
            if action == "keep":
                continue
            try:
                priority = max(0.0, min(1.0, float(item.get("priority", 0.5))))
            except (TypeError, ValueError):
                priority = 0.5
            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
            except (TypeError, ValueError):
                confidence = 0.5
            params = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
            out.append({
                "scene": scene_no,
                "action": action,
                "reason": [str(x) for x in (item.get("reason") or ["creative signal"])][:5],
                "priority": round(priority, 4),
                "confidence": round(confidence, 4),
                "parameters": params,
            })
            seen.add(scene_no)
            if len(out) >= max_changes:
                break
        return {"changes": out}

    def _execution_summary(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        executable = []
        manual = []
        for change in changes:
            action = change["action"]
            if action in {"replace_visual", "tighten"}:
                executable.append(change)
            else:
                manual.append(change)
        return {
            "automatic": len(executable),
            "manual_review": len(manual),
            "supported_actions": ["replace_visual", "tighten"],
        }

    def _empty_plan(self, project, reason: str) -> dict[str, Any]:
        return {
            "status": "NO_CHANGE",
            "source_project_id": str(getattr(project, "id", "")),
            "changes": [],
            "execution": {"automatic": 0, "manual_review": 0, "supported_actions": ["replace_visual", "tighten"]},
            "reason": reason,
        }
