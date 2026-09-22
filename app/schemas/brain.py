from pydantic import BaseModel, Field


class BrainRebuildRequest(BaseModel):
    min_video_count: int = Field(default=3, ge=1, le=500)


class VideoOptimizationRequest(BaseModel):
    video_id: str = Field(min_length=1, max_length=128)
    start_date: str
    end_date: str


class BrainResponse(BaseModel):
    channel_id: str
    source_video_count: int
    version: int
    summary: str
    learned_patterns: list
    topic_clusters: list
    hook_patterns: list
    title_patterns: list
    pacing_patterns: list
    production_notes: list
