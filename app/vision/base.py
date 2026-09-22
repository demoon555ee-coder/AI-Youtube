from abc import ABC, abstractmethod
from typing import Any


class VisionProvider(ABC):
    name: str

    @abstractmethod
    async def analyze_frame(self, *, image_path: str, prompt: str) -> dict[str, Any]:
        raise NotImplementedError

    async def analyze_multimodal(self, *, image_paths: list[str], prompt: str) -> dict[str, Any]:
        """Default compatibility path for providers that only understand one image at a time."""
        if not image_paths:
            return {"_provider": getattr(self, "name", "unknown"), "scene_findings": []}
        results = []
        for path in image_paths:
            results.append(await self.analyze_frame(image_path=path, prompt=prompt))
        return {
            "overall_alignment": round(sum(float(r.get("narration_visual_alignment", 0.0) or 0) for r in results) / max(1, len(results)), 4),
            "storyboard_adherence": round(sum(float(r.get("relevance_score", 0.0) or 0) for r in results) / max(1, len(results)), 4),
            "visual_variety": round(sum(float(r.get("clarity_score", 0.0) or 0) for r in results) / max(1, len(results)), 4),
            "scene_findings": [],
            "recommended_actions": [],
            "_provider": getattr(self, "name", "unknown"),
            "_fallback": True,
        }
