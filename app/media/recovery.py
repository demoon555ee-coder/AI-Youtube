from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.media.factory import get_video_provider
from app.models import MediaGenerationJob, ProviderProfile


class MediaRecoveryService:
    """Recover submitted async media jobs after worker interruption.

    Only providers exposing the generic HTTP video contract are auto-recovered. Unknown
    provider kinds are moved to RETRY/DEAD_LETTER instead of guessing their APIs.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_due(self, limit: int | None = None) -> int:
        if not settings.media_recovery_enabled:
            return 0
        limit = limit or settings.media_recovery_batch_size
        now = datetime.utcnow()
        q = await self.db.execute(
            select(MediaGenerationJob)
            .where(
                MediaGenerationJob.status.in_({"SUBMITTED", "PROCESSING", "RETRY"}),
                or_(MediaGenerationJob.next_poll_at.is_(None), MediaGenerationJob.next_poll_at <= now),
            )
            .order_by(MediaGenerationJob.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        jobs = list(q.scalars().all())
        for job in jobs:
            job.status = "RECOVERING"
            job.attempts += 1
            job.next_poll_at = now + timedelta(seconds=settings.media_recovery_lease_seconds)
        await self.db.commit()

        recovered = 0
        for job in jobs:
            try:
                if job.provider != "http_video" or not job.status_url or not job.local_output_path or not job.portfolio_id:
                    await self._fail_or_retry(job, "unsupported recovery provider or missing status_url/output path")
                    continue
                profile = await self.db.scalar(
                    select(ProviderProfile).where(ProviderProfile.portfolio_id == job.portfolio_id, ProviderProfile.provider == job.provider, ProviderProfile.service == "video", ProviderProfile.enabled.is_(True)).order_by(ProviderProfile.priority.desc()).limit(1)
                )
                config = (profile.config_json or {}) if profile else {}
                provider = get_video_provider(job.provider, config)
                result = await provider.recover_existing_job(
                    status_url=job.status_url,
                    output_path=job.local_output_path,
                    external_job_id=job.external_job_id,
                    output_url=job.output_url,
                )
                async with self.db.begin():
                    job = await self.db.get(MediaGenerationJob, job.id, with_for_update=True)
                    job.status = "COMPLETED"
                    job.output_url = result.get("download_url") or job.output_url
                    job.status_url = result.get("status_url") or job.status_url
                    job.local_output_path = result.get("path")
                    job.result_json = result
                    job.error_message = None
                    job.completed_at = datetime.utcnow()
                    job.next_poll_at = None
                recovered += 1
            except Exception as exc:
                await self._fail_or_retry(job, str(exc))
        return recovered

    async def _fail_or_retry(self, job: MediaGenerationJob, reason: str) -> None:
        async with self.db.begin():
            current = await self.db.get(MediaGenerationJob, job.id, with_for_update=True)
            if not current:
                return
            current.error_message = reason[:2000]
            if current.attempts >= settings.media_job_max_attempts:
                current.status = "DEAD_LETTER"
                current.next_poll_at = None
            else:
                current.status = "RETRY"
                current.next_poll_at = datetime.utcnow() + timedelta(seconds=min(300, 2 ** max(current.attempts - 1, 0)))
