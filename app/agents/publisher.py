from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.base import BaseAgent
from app.services.youtube_service import publish


@dataclass(slots=True)
class PublishPayload:
    title: str | None = None
    description: str = ""
    tags: list[str] = None  # type: ignore[assignment]
    category_id: str = "22"
    privacy_status: str = "private"
    publish_at: str | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []


class YouTubePublisherAgent(BaseAgent):
    """Thin YouTube adapter; authorization remains entirely in Governance + Runtime."""

    name = "publisher"

    def __init__(self, db):
        self.db = db

    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(input_data["channel_id"])
        project_id = str(input_data["project_id"])
        payload = PublishPayload(
            title=input_data.get("title"),
            description=str(input_data.get("description") or ""),
            tags=list(input_data.get("tags") or []),
            category_id=str(input_data.get("category_id") or "22"),
            privacy_status=str(input_data.get("privacy_status") or "private"),
            publish_at=input_data.get("publish_at"),
        )
        return await publish(self.db, channel_id, project_id, payload)
