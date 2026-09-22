from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=60)


class ActivatePlanRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=60)
    provider_subscription_reference: str | None = Field(default=None, max_length=255)


class CancelSubscriptionRequest(BaseModel):
    at_period_end: bool = True


class MeterRequest(BaseModel):
    service: str = Field(min_length=1, max_length=100)
    units: float = Field(gt=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    action: str = Field(default="usage", min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=255)
    channel_id: str | None = None
    project_id: str | None = None
    metadata: dict = Field(default_factory=dict)
