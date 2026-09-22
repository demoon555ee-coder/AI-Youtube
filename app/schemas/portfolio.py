from pydantic import BaseModel, Field


class PortfolioConfigureRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    name: str | None = Field(default=None, max_length=255)
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    daily_budget_usd: float | None = Field(default=None, ge=0)


class PortfolioChannelRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    budget_weight: float = Field(default=1.0, ge=0)
    monthly_budget_usd: float = Field(default=0, ge=0)


class ProviderBudgetRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=100)
    service: str = Field(default="general", min_length=1, max_length=100)
    monthly_limit_usd: float = Field(default=0, ge=0)
    daily_limit_usd: float = Field(default=0, ge=0)
    hard_limit: bool = False


class CostEventRequest(BaseModel):
    owner_id: str = Field(default="local-user", min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=100)
    service: str = Field(default="general", min_length=1, max_length=100)
    unit: str = Field(default="request", min_length=1, max_length=50)
    quantity: float = Field(default=1, ge=0)
    unit_cost_usd: float = Field(default=0, ge=0)
    channel_id: str | None = None
    project_id: str | None = None
    agent_run_id: str | None = None
    metadata: dict = Field(default_factory=dict)
