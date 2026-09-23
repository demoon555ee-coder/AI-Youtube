from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.media.factory import get_image_provider, get_video_provider


class AssetFactory:
    """Build scene assets using routed image/video providers.

    The factory keeps image and video provider selection separate so a storyboard can
    mix static scenes, generated motion, and stock B-roll without coupling the workflow
    to a single vendor. Provider attribution is preserved in the manifest for publishing.
    """

    def __init__(
        self,
        output_dir: str,
        *,
        image_provider: str | None = None,
        image_config: dict | None = None,
        video_provider: str | None = None,
        video_config: dict | None = None,
        media_job_callback=None,
        media_job_context: dict[str, Any] | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.image_provider = get_image_provider(image_provider, image_config)
        self.video_provider = get_video_provider(video_provider, video_config)
        self.media_job_callback = media_job_callback
        self.media_job_context = media_job_context or {}

    @staticmethod
    def _is_motion_asset(scene: dict[str, Any]) -> bool:
        return str(scene.get("asset_type", "image")).strip().lower() in {"video", "broll"}

    async def build_for_storyboard(
        self,
        *,
        project_id: str,
        storyboard: dict[str, Any],
        scene_routes: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        project_dir = self.output_dir / project_id / "assets"
        project_dir.mkdir(parents=True, exist_ok=True)
        assets: list[dict[str, Any]] = []

        for scene in storyboard.get("scenes", []):
            scene_no = int(scene.get("scene", len(assets) + 1))
            duration = max(float(scene.get("duration", 5)), 0.5)
            visual_prompt = str(
                scene.get("visual_prompt")
                or scene.get("visual")
                or "cinematic YouTube visual"
            )
            motion = self._is_motion_asset(scene)
            route = (scene_routes or {}).get(str(scene_no)) or {}
            routed_provider = route.get("video" if motion else "image")
            if routed_provider:
                provider = get_video_provider(routed_provider.get("provider"), routed_provider.get("config") or {}) if motion else get_image_provider(routed_provider.get("provider"), routed_provider.get("config") or {})
            else:
                provider = self.video_provider if motion else self.image_provider
            output_path = project_dir / f"scene_{scene_no:03d}{'.mp4' if motion else '.png'}"
            metadata = {"scene": scene_no, "asset_type": scene.get("asset_type", "image")}
            if routed_provider:
                metadata["routing_decision_id"] = routed_provider.get("decision_id")
                metadata["routing_reason"] = routed_provider.get("reason")
            metadata["idempotency_key"] = f"{self.media_job_context.get('project_id', project_id)}:{self.media_job_context.get('attempt', 1)}:{scene_no}"
            if motion and provider.name == "runway":
                source_image = str(
                    scene.get("source_image")
                    or scene.get("reference_image")
                    or scene.get("image_path")
                    or ""
                ).strip()
                if not source_image:
                    seed_path = project_dir / f"seed_scene_{scene_no:03d}.png"
                    seed_result = await self.image_provider.generate_scene_asset(
                        prompt=visual_prompt,
                        output_path=str(seed_path),
                        width=1920,
                        height=1080,
                        duration_seconds=duration,
                        metadata={
                            "scene": scene_no,
                            "asset_type": "image_seed",
                            "purpose": "runway_first_frame",
                        },
                    )
                    source_image = str(seed_result["path"])
                metadata["image_path"] = source_image
            if motion and self.media_job_callback:
                metadata["on_submitted"] = self.media_job_callback
            result = await provider.generate_scene_asset(
                prompt=visual_prompt,
                output_path=str(output_path),
                duration_seconds=duration,
                metadata=metadata,
            )
            assets.append(
                {
                    "id": f"asset_{scene_no:03d}",
                    "scene": scene_no,
                    "kind": "visual",
                    "source": result["provider"],
                    "path": result["path"],
                    "prompt": visual_prompt,
                    "asset_type": "video" if motion else scene.get("asset_type", "image"),
                    "visual_goal": scene.get("visual_goal", ""),
                    "shot": scene.get("shot", "medium"),
                    "motion": scene.get("motion", "slow_push_in"),
                    "transition": scene.get("transition", "cut"),
                    "duration_seconds": duration,
                    "external_job_id": result.get("external_job_id"),
                    "routing": routed_provider,
                    "source_url": result.get("source_url"),
                    "attribution": result.get("attribution"),
                    "usage": result.get("usage", {}),
                    "status": result.get("status", "ready"),
                }
            )

        manifest = {
            "project_id": project_id,
            "providers": {
                "image": self.image_provider.name,
                "video": self.video_provider.name,
            },
            "assets": assets,
            "attribution": [
                asset["attribution"]
                for asset in assets
                if asset.get("attribution")
            ],
        }
        manifest_path = project_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "status": "ready",
            "providers": manifest["providers"],
            "manifest_path": str(manifest_path),
            "assets": assets,
            "attribution": manifest["attribution"],
        }
