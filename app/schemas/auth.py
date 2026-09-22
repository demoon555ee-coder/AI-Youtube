from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(default="", max_length=255)
    organization_name: str = Field(default="My YouTube Studio", min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=256)
    organization_id: str | None = None


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class MemberAddRequest(BaseModel):
    email: str
    role: str = Field(default="viewer", pattern="^(owner|admin|editor|analyst|viewer)$")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class UsageEventRequest(BaseModel):
    service: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=100)
    units: float = Field(default=1.0, ge=0)
    unit: str = Field(default="request", min_length=1, max_length=50)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    channel_id: str | None = None
    project_id: str | None = None
    metadata: dict = Field(default_factory=dict)
