from pydantic import BaseModel, Field


class PortfolioPolicyRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    planning_horizon_days: int | None = Field(default=None, ge=1, le=365)
    reserve_ratio: float | None = Field(default=None, ge=0, le=0.95)
    target_utilization_pct: float | None = Field(default=None, ge=1, le=100)
    max_channel_concentration_pct: float | None = Field(default=None, ge=1, le=100)
    min_channel_allocation_usd: float | None = Field(default=None, ge=0)
    min_daily_buffer_usd: float | None = Field(default=None, ge=0)
    enabled: bool | None = None


class ReserveRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    amount_usd: float = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=255)
    channel_id: str | None = None
    project_id: str | None = None
    purpose: str = Field(default="production", max_length=100)
    ttl_minutes: int = Field(default=60, ge=1, le=10080)


class ForecastRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    days: int = Field(default=30, ge=1, le=365)
    average_video_cost_usd: float = Field(default=1.0, ge=0)
