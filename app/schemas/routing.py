from pydantic import BaseModel, Field


class ProviderProfileRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=100)
    service: str = Field(default="llm", min_length=1, max_length=100)
    kind: str = Field(default="mock", min_length=1, max_length=100)
    quality_tier: str = Field(default="standard", pattern="^(economy|standard|premium)$")
    priority: int = Field(default=100, ge=0, le=10000)
    unit: str = Field(default="request", min_length=1, max_length=50)
    unit_cost_usd: float = Field(default=0, ge=0)
    capabilities: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class RouteRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    service: str = Field(min_length=1, max_length=100)
    requested_tier: str = Field(default="standard", pattern="^(economy|standard|premium)$")
    units: float = Field(default=1, ge=0)
    channel_id: str | None = None
    project_id: str | None = None
    step_name: str = Field(default="manual", max_length=100)
    required_capabilities: list[str] = Field(default_factory=list)
    allow_quality_downgrade: bool = True


class ProjectRouteRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    channel_id: str
    project_id: str
    goal: str = Field(default="balanced", max_length=30)
    quality_mode: str = Field(default="balanced", pattern="^(cost|balanced|quality|premium)$")
