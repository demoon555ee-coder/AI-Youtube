from __future__ import annotations
from typing import Any
from app.vision.base import VisionProvider


class MockVisionProvider(VisionProvider):
    name = "mock"

    async def analyze_frame(self, *, image_path: str, prompt: str) -> dict[str, Any]:
        return {
            "relevance_score": 0.82,
            "clarity_score": 0.80,
            "narration_visual_alignment": 0.84,
            "issues": [],
            "recommendations": [],
            "objects": ["visual_content"],
            "_provider": self.name,
        }

    async def analyze_multimodal(self, *, image_paths: list[str], prompt: str) -> dict[str, Any]:
        return {
            "overall_alignment": 0.84,
            "storyboard_adherence": 0.86,
            "visual_variety": 0.81,
            "scene_findings": [],
            "recommended_actions": [],
            "images_analyzed": len(image_paths),
            "_provider": self.name,
        }
