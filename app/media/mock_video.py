from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.media.base import VisualAssetProvider


class MockVideoProvider(VisualAssetProvider):
    """Creates a tiny deterministic MP4 through FFmpeg for offline tests."""

    name = "mock_video"

    async def generate_scene_asset(self, *, prompt: str, output_path: str, width: int = 1920, height: int = 1080, duration_seconds: float = 5.0, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = Path(output_path).with_suffix(".mp4")
        path.parent.mkdir(parents=True, exist_ok=True)
        scene = int((metadata or {}).get("scene", 1))
        hue = (scene * 37) % 360
        # Stable test fixture; production deployments use a real provider.
        filter_expr = f"hue=h={hue}:s=0.55,format=yuv420p"
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x1f2937:s={width}x{height}:r=24",
            "-t", f"{max(0.5, duration_seconds):.3f}", "-vf", filter_expr,
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace")[-2000:])
        result = {"provider": self.name, "path": str(path), "media_type": "video/mp4", "duration_seconds": duration_seconds, "prompt": prompt, "external_job_id": f"mock-{scene}"}
        callback = (metadata or {}).get("on_submitted")
        if callback:
            await callback({"provider": self.name, "external_job_id": result["external_job_id"], "status": "completed", "output_path": str(path), "scene": scene, "idempotency_key": (metadata or {}).get("idempotency_key")})
        return result
