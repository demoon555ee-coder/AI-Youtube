from __future__ import annotations

import json
from typing import Any
from app.agents.base import BaseAgent
from app.providers.base import LLMProvider


class SceneDirectorAgent(BaseAgent):
    name = "scene_director"

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        storyboard = input_data["storyboard"]
        if getattr(self.llm, "name", "") == "mock":
            return self._deterministic(storyboard)
        result = await self.llm.generate_json(
            system=(
                "Return JSON with scenes[]. For each scene include scene, duration, narration, "
                "asset_type (image|video|broll|graphic), visual_goal, visual_prompt, shot, motion, "
                "on_screen_text, transition, audio_cue. Keep scene numbering and durations aligned."
            ),
            user=json.dumps(storyboard, ensure_ascii=False),
        )
        return self._normalize(result, storyboard)

    def _normalize(self, result: dict[str, Any], storyboard: dict[str, Any]) -> dict[str, Any]:
        raw = result.get("scenes") if isinstance(result.get("scenes"), list) else []
        fallback = self._deterministic(storyboard)["scenes"]
        scenes = []
        for i, base in enumerate(fallback):
            candidate = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
            merged = {**base, **candidate, "scene": i + 1, "duration": max(float(candidate.get("duration", base["duration"])), 1.0)}
            scenes.append(merged)
        return {"scenes": scenes, "director_notes": result.get("director_notes", [])}

    def _deterministic(self, storyboard: dict[str, Any]) -> dict[str, Any]:
        scenes = []
        for i, scene in enumerate(storyboard.get("scenes", []), start=1):
            kind = "graphic" if i % 5 == 0 else "video" if i % 3 == 0 else "image"
            scenes.append({
                "scene": i,
                "duration": max(float(scene.get("duration", 5)), 1.0),
                "narration": scene.get("narration", ""),
                "asset_type": kind,
                "visual_goal": "Support the narration with one clear visual idea.",
                "visual_prompt": scene.get("visual_prompt") or scene.get("visual") or "cinematic documentary visual",
                "shot": scene.get("shot", "medium"),
                "motion": scene.get("motion", "slow_push_in"),
                "on_screen_text": scene.get("on_screen_text", ""),
                "transition": "cut" if i % 4 else "dissolve",
                "audio_cue": "narration_first",
            })
        return {"scenes": scenes, "director_notes": ["Deterministic scene plan; replace with an LLM provider for semantic shot planning."]}
