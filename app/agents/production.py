from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.media import AssetFactory
from app.config import settings
from app.models import MediaGenerationJob


class ProductionAgent(BaseAgent):
    name = "production"

    def __init__(self, image_provider: str | None = None, image_config: dict | None = None, video_provider: str | None = None, video_config: dict | None = None, db=None, organization_id=None, portfolio_id=None, channel_id=None, agent_run_id=None, workflow_attempt: int = 1):
        self.db = db
        self.organization_id = organization_id
        self.portfolio_id = portfolio_id
        self.channel_id = channel_id
        self.agent_run_id = agent_run_id
        self.workflow_attempt = workflow_attempt
        self.assets = AssetFactory(
            settings.output_dir,
            image_provider=image_provider,
            image_config=image_config,
            video_provider=video_provider,
            video_config=video_config,
            media_job_callback=self._on_video_submitted if db is not None else None,
            media_job_context={"project_id": "pending", "attempt": workflow_attempt},
        )

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        storyboard = input_data.get("scene_director") or input_data["storyboard"]
        project_id = str(input_data["project_id"])
        self.assets.media_job_context["project_id"] = project_id
        return await self.assets.build_for_storyboard(project_id=project_id, storyboard=storyboard)

    async def _on_video_submitted(self, info: dict[str, Any]) -> None:
        if self.db is None:
            return
        project_id = __import__('uuid').UUID(self.assets.media_job_context['project_id'])
        idem = info.get("idempotency_key") or f"{project_id}:{self.workflow_attempt}:{info.get('scene', 0)}"
        from sqlalchemy import select
        existing = await self.db.scalar(select(MediaGenerationJob).where(MediaGenerationJob.idempotency_key == str(idem)).with_for_update())
        if existing is None:
            job = MediaGenerationJob(
                organization_id=self.organization_id,
                portfolio_id=self.portfolio_id,
                channel_id=self.channel_id,
                project_id=project_id,
                agent_run_id=self.agent_run_id,
                scene_number=int(info.get("scene", 0)),
                provider=str(info.get("provider") or self.video_provider_name),
                external_job_id=str(info.get("external_job_id") or "") or None,
                idempotency_key=str(idem),
                status="COMPLETED" if info.get("status") == "completed" else "SUBMITTED",
                status_url=info.get("status_url"),
                output_url=info.get("download_url"),
                local_output_path=info.get("output_path"),
                request_json={"scene": info.get("scene"), "idempotency_key": idem},
                result_json=info,
                completed_at=__import__('datetime').datetime.utcnow() if info.get("status") == "completed" else None,
            )
            self.db.add(job)
        else:
            existing.external_job_id = existing.external_job_id or (str(info.get("external_job_id")) if info.get("external_job_id") else None)
            existing.status_url = existing.status_url or info.get("status_url")
            existing.output_url = existing.output_url or info.get("download_url")
            existing.local_output_path = existing.local_output_path or info.get("output_path")
            existing.status = "COMPLETED" if info.get("status") == "completed" else existing.status
            existing.result_json = info
            if info.get("status") == "completed":
                existing.completed_at = __import__('datetime').datetime.utcnow()
        # Commit immediately so a worker crash during a long provider poll leaves a recoverable job.
        await self.db.commit()

    @property
    def video_provider_name(self):
        return self.assets.video_provider.name
