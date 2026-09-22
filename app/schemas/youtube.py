from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class YouTubeOAuthStart(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)


class PublishRequest(BaseModel):
    project_id: str
    title: str | None = Field(default=None, max_length=100)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    category_id: str = "22"
    privacy_status: str = "private"
    publish_at: str | None = None

    @field_validator("privacy_status")
    @classmethod
    def validate_privacy(cls, value: str) -> str:
        if value not in {"private", "unlisted", "public"}:
            raise ValueError("privacy_status must be private, unlisted, or public")
        return value

    @field_validator("publish_at")
    @classmethod
    def validate_publish_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("publish_at must be an ISO-8601 datetime") from exc
        return value


class AnalyticsRequest(BaseModel):
    start_date: str
    end_date: str
    video_id: str | None = None
