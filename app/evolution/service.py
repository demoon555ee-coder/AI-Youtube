from __future__ import annotations

import copy
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ContentArtifact, ContentVersion, PerformanceAlert, VideoProject


class ContentEvolutionService:
    """Create immutable project revisions without modifying the source project."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_revision(
        self,
        *,
        source_project: VideoProject,
        trigger_type: str,
        reason: str,
        change_plan: dict[str, Any],
        metrics_snapshot: dict[str, Any] | None = None,
        trigger_alert_id: UUID | None = None,
    ) -> tuple[VideoProject, ContentVersion]:
        root_id = source_project.content_root_id or source_project.id
        # Serialize allocation of a revision number across concurrent recovery requests.
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('content_revision:' || CAST(:root_id AS text)))"),
            {"root_id": str(root_id)},
        )
        max_q = await self.db.execute(
            select(ContentVersion.revision_number)
            .where(ContentVersion.content_root_id == root_id)
            .order_by(ContentVersion.revision_number.desc())
            .limit(1)
            .with_for_update()
        )
        last_revision = max_q.scalar_one_or_none()
        next_revision = int(last_revision if last_revision is not None else source_project.revision_number or 0) + 1

        data = copy.deepcopy(source_project.data or {})
        for volatile in ("research", "script", "storyboard", "scene_director", "production", "editor", "thumbnail", "qa", "routing_plan"):
            data.pop(volatile, None)
        data["evolution"] = {
            "revision_number": next_revision,
            "root_project_id": str(root_id),
            "parent_project_id": str(source_project.id),
            "trigger_type": trigger_type,
            "reason": reason,
            "change_plan": change_plan,
            "metrics_snapshot": metrics_snapshot or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        if change_plan.get("title"):
            data["title"] = change_plan["title"]
        if change_plan.get("hook"):
            data["hook"] = change_plan["hook"]
        if change_plan.get("angle"):
            data["angle"] = change_plan["angle"]

        revision_project = VideoProject(
            channel_id=source_project.channel_id,
            topic=source_project.topic,
            status="IDEA",
            data=data,
            content_root_id=root_id,
            parent_project_id=source_project.id,
            revision_number=next_revision,
        )
        self.db.add(revision_project)
        await self.db.flush()

        version = ContentVersion(
            project_id=revision_project.id,
            content_root_id=root_id,
            parent_project_id=source_project.id,
            revision_number=next_revision,
            trigger_type=trigger_type,
            trigger_alert_id=trigger_alert_id,
            reason=reason,
            change_plan=change_plan,
            metrics_snapshot=metrics_snapshot or {},
            status="DRAFT",
        )
        self.db.add(version)
        await self.db.flush()
        return revision_project, version

    async def list_versions(self, root_id: UUID) -> list[ContentVersion]:
        q = await self.db.execute(
            select(ContentVersion)
            .where(ContentVersion.content_root_id == root_id)
            .order_by(ContentVersion.revision_number.asc())
        )
        return list(q.scalars().all())

    async def update_status(self, project_id: UUID, status: str) -> None:
        row = await self.db.scalar(select(ContentVersion).where(ContentVersion.project_id == project_id).with_for_update())
        if row:
            row.status = status
            row.updated_at = datetime.utcnow()
            await self.db.flush()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    async def register_project_artifacts(self, project: VideoProject) -> list[ContentArtifact]:
        output_root = Path(settings.output_dir).resolve()
        data = project.data or {}
        candidates: list[tuple[str, str | None, dict[str, Any]]] = []
        editor = data.get("editor") or {}
        candidates.append(("video", editor.get("output_path"), {"source": "editor"}))
        candidates.append(("subtitles", editor.get("subtitle_path"), {"source": "editor"}))
        thumbnail = data.get("thumbnail") or {}
        candidates.append(("thumbnail", thumbnail.get("path"), {"source": "thumbnail"}))
        production = data.get("production") or {}
        candidates.append(("production_manifest", production.get("manifest_path"), {"source": "production"}))
        for asset in production.get("assets") or []:
            candidates.append(("scene_asset", asset.get("path"), {"source": "production", "scene": asset.get("scene"), "provider": asset.get("source")}))

        saved: list[ContentArtifact] = []
        for artifact_type, raw_path, metadata in candidates:
            if not raw_path:
                continue
            path = Path(str(raw_path)).resolve()
            try:
                relative = path.relative_to(output_root).as_posix()
            except ValueError:
                continue
            if not path.is_file():
                continue
            digest = self._sha256_file(path)
            existing = await self.db.scalar(
                select(ContentArtifact).where(
                    ContentArtifact.project_id == project.id,
                    ContentArtifact.artifact_type == artifact_type,
                    ContentArtifact.relative_path == relative,
                )
            )
            if existing:
                existing.sha256 = digest
                existing.size_bytes = path.stat().st_size
                existing.metadata_json = metadata
                saved.append(existing)
                continue
            row = ContentArtifact(
                project_id=project.id,
                artifact_type=artifact_type,
                relative_path=relative,
                sha256=digest,
                size_bytes=path.stat().st_size,
                immutable=True,
                metadata_json=metadata,
            )
            self.db.add(row)
            saved.append(row)
        await self.db.flush()
        return saved


def build_evolution_plan(*, alert_type: str | None = None, metric: str | None = None, delta_pct: float | None = None, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    metric = (metric or alert_type or "video").lower()
    change_plan: dict[str, Any] = {
        "objective": "improve observed weak performance without changing the source revision",
        "do_not_modify_source": True,
        "preserve_topic": True,
    }
    if metric in {"retention", "average_view_percentage", "opening"}:
        change_plan.update({"hook": "strengthen first 20 seconds with an earlier promise and faster payoff", "pacing": "increase visual/narrative changes in the opening third", "sections": ["shorten_intro", "move_first_reveal_earlier"]})
    elif metric in {"ctr", "impression_ctr", "thumbnail", "title"}:
        change_plan.update({"packaging": "test one clearer title angle and one stronger thumbnail composition", "experiment_dimension": "title_or_thumbnail"})
    elif metric == "views":
        change_plan.update({"packaging": "refine title/thumbnail", "topic_angle": "make the value proposition more explicit", "hook": "state the payoff earlier"})
    else:
        change_plan.update({"review": "rework weak section while preserving factual claims and topic"})
    change_plan["observed_delta_pct"] = delta_pct
    change_plan["evidence"] = evidence or {}
    return change_plan
