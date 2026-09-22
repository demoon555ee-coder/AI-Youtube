from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.content import IdeaGenerationRequest
from app.content.service import generate_ideas, list_ideas, select_idea, create_project_from_selected_idea

router = APIRouter(prefix="/api/v1/content", tags=["content-strategy"])


@router.post("/channels/{channel_id}/generate-ideas")
async def content_generate_ideas(channel_id: str, payload: IdeaGenerationRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await generate_ideas(
            db,
            channel_id=channel_id,
            seed_topics=payload.seed_topics,
            count=payload.count,
            goal=payload.goal,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/channels/{channel_id}/ideas")
async def content_list_ideas(channel_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    try:
        rows = await list_ideas(db, channel_id, min(max(limit, 1), 100))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "channel_id": channel_id,
        "ideas": [
            {
                "id": str(row.id),
                "topic": row.topic,
                "title": row.title,
                "hook": row.hook,
                "angle": row.angle,
                "duration_minutes": row.target_duration_minutes,
                "demand_signal": row.demand_signal,
                "competition_signal": row.competition_signal,
                "channel_fit": row.channel_fit,
                "novelty": row.novelty,
                "production_cost": row.production_cost,
                "composite_score": row.composite_score,
                "status": row.status,
                "selected": row.selected,
                "research_opportunity_id": str(row.research_opportunity_id) if row.research_opportunity_id else None,
            } for row in rows
        ],
    }


@router.post("/channels/{channel_id}/ideas/{idea_id}/select")
async def content_select_idea(channel_id: str, idea_id: str, db: AsyncSession = Depends(get_db)):
    try:
        idea = await select_idea(db, channel_id, idea_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"id": str(idea.id), "status": idea.status, "selected": idea.selected, "title": idea.title}


@router.post("/channels/{channel_id}/ideas/{idea_id}/create-project")
async def content_create_project(channel_id: str, idea_id: str, db: AsyncSession = Depends(get_db)):
    try:
        project = await create_project_from_selected_idea(db, channel_id, idea_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"project_id": str(project.id), "topic": project.topic, "status": project.status}
