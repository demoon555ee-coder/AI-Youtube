from __future__ import annotations
from typing import Any
from app.agents.base import BaseAgent


class StoryboardAgent(BaseAgent):
    name = "storyboard"

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        script = input_data["script"]
        scenes = []
        for i, section in enumerate(script.get("sections", []), start=1):
            text = str(section.get("text", ""))
            section_type = str(section.get("type", "main"))
            title = text[:100]
            scenes.append({
                "scene": i,
                "duration": max(float(section.get("duration", 5)), 1.0),
                "narration": text,
                "visual": f"Cinematic {section_type} visual illustrating: {title}",
                "visual_prompt": (
                    f"cinematic documentary YouTube b-roll, {section_type}, "
                    f"visually explain this narration: {text[:220]}"
                ),
                "on_screen_text": section_type.upper(),
                "shot": "wide" if i % 3 == 1 else "medium" if i % 3 == 2 else "close",
                "motion": "slow_push_in" if i % 2 else "lateral_motion",
            })
        return {"scenes": scenes, "title": script.get("title", ""), "hook": script.get("hook", "")}
