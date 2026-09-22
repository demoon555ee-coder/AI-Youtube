from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.content.intelligence_service import build_for_idea, list_blueprints, serialize_blueprint
from app.content.service import load_channel_memory

router = APIRouter(prefix="/api/v1/intelligence", tags=["content-intelligence"])


class BlueprintRequest(BaseModel):
    goal: str = Field(default="balanced", pattern="^(growth|authority|monetization|balanced)$")
    plan_item_id: str | None = None
    project_id: str | None = None


@router.get("/channels/{channel_id}/overview")
async def intelligence_overview(channel_id: str, db: AsyncSession = Depends(get_db)):
    memory = await load_channel_memory(db, channel_id)
    blueprints = await list_blueprints(db, channel_id=channel_id, limit=20)
    format_counts: dict[str, int] = {}
    hook_counts: dict[str, int] = {}
    for item in blueprints:
        format_counts[item.format] = format_counts.get(item.format, 0) + 1
        hook_counts[item.hook_pattern] = hook_counts.get(item.hook_pattern, 0) + 1
    return {
        "channel_id": channel_id,
        "memory_version": memory.get("version", 0),
        "learned_patterns": memory.get("learned_patterns", []),
        "format_usage": format_counts,
        "hook_usage": hook_counts,
        "blueprint_count": len(blueprints),
    }


@router.get("/channels/{channel_id}/blueprints")
async def intelligence_blueprints(channel_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = await list_blueprints(db, channel_id=channel_id, limit=limit)
    return {"channel_id": channel_id, "blueprints": [serialize_blueprint(x) for x in rows]}


@router.post("/channels/{channel_id}/ideas/{idea_id}/blueprint")
async def intelligence_blueprint(channel_id: str, idea_id: str, payload: BlueprintRequest, db: AsyncSession = Depends(get_db)):
    try:
        row = await build_for_idea(
            db,
            channel_id=channel_id,
            idea_id=idea_id,
            goal=payload.goal,
            plan_item_id=payload.plan_item_id,
            project_id=payload.project_id,
        )
        return serialize_blueprint(row)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
