from datetime import datetime
from pydantic import BaseModel, Field


class ExperimentCreateRequest(BaseModel):
    dimension: str = Field(pattern="^(title|thumbnail|hook|pacing|topic_angle)$")
    hypothesis: str = ""
    experiment_type: str = "observational"
    video_project_id: str | None = None
    variants: dict = Field(default_factory=dict)
    decision_rule: dict = Field(default_factory=lambda: {"primary_metric": "average_view_percentage", "minimum_observations": 2})


class ExperimentObservationRequest(BaseModel):
    variant_key: str = Field(min_length=1, max_length=100)
    observed_at: datetime | None = None
    views: int = Field(default=0, ge=0)
    impressions: int = Field(default=0, ge=0)
    ctr: float = Field(default=0, ge=0)
    average_view_percentage: float = Field(default=0, ge=0)
    watch_time_minutes: float = Field(default=0, ge=0)
    subscribers_gained: int = Field(default=0, ge=0)
    raw: dict = Field(default_factory=dict)
