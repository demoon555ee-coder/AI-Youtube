from pydantic import BaseModel, Field


class IdeaGenerationRequest(BaseModel):
    seed_topics: list[str] = Field(default_factory=list, max_length=30)
    count: int = Field(default=10, ge=1, le=50)
    goal: str = Field(default="balanced", pattern="^(growth|authority|monetization|balanced)$")


class IdeaResponse(BaseModel):
    id: str
    topic: str
    title: str
    hook: str
    angle: str
    duration_minutes: int
    demand_signal: float
    competition_signal: float
    channel_fit: float
    novelty: float
    production_cost: float
    composite_score: float
    status: str
    selected: bool
