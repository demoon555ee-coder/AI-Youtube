from datetime import date
from pydantic import BaseModel, Field, field_validator


class AutopilotPlanCreateRequest(BaseModel):
    name: str = Field(default="30-Day Content Plan", min_length=1, max_length=255)
    start_date: date
    horizon_days: int = Field(default=30, ge=1, le=365)
    cadence_per_week: int = Field(default=3, ge=1, le=7)
    publish_time: str = Field(default="18:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    goal: str = Field(default="balanced", pattern="^(growth|authority|monetization|balanced)$")
    timezone: str | None = Field(default=None, max_length=64)
    production_lead_hours: int = Field(default=24, ge=0, le=168)
    auto_publish: bool = False
    seed_topics: list[str] = Field(default_factory=list, max_length=30)


class MaterializeRequest(BaseModel):
    item_ids: list[str] | None = Field(default=None, max_length=365)


class PlanActionResponse(BaseModel):
    id: str
    status: str
