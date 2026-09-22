from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models import ContentExperiment
from app.schemas.experiments import ExperimentCreateRequest, ExperimentObservationRequest
from app.experiments import ExperimentEngine

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])
engine = ExperimentEngine()


def _serialize(exp: ContentExperiment) -> dict:
    return {
        "id": str(exp.id),
        "channel_id": str(exp.channel_id),
        "video_project_id": str(exp.video_project_id) if exp.video_project_id else None,
        "experiment_type": exp.experiment_type,
        "dimension": exp.dimension,
        "hypothesis": exp.hypothesis,
        "variants": exp.variants,
        "decision_rule": exp.decision_rule,
        "status": exp.status,
        "started_at": exp.started_at,
        "ended_at": exp.ended_at,
        "result": exp.result,
    }


@router.get("/channels/{channel_id}")
async def list_experiments(channel_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    q = await db.execute(
        select(ContentExperiment).where(ContentExperiment.channel_id == UUID(channel_id)).order_by(ContentExperiment.created_at.desc()).limit(min(max(limit, 1), 100))
    )
    return {"channel_id": channel_id, "experiments": [_serialize(x) for x in q.scalars().all()]}


@router.post("/channels/{channel_id}")
async def create_experiment(channel_id: str, payload: ExperimentCreateRequest, db: AsyncSession = Depends(get_db)):
    try:
        exp = await engine.create_manual(db, channel_id=channel_id, payload=payload.model_dump())
        return _serialize(exp)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/channels/{channel_id}/from-optimization/{report_id}")
async def create_from_optimization(channel_id: str, report_id: str, db: AsyncSession = Depends(get_db)):
    try:
        exp = await engine.create_from_report(db, channel_id=channel_id, report_id=report_id)
        return _serialize(exp)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{experiment_id}/observations")
async def add_observation(experiment_id: str, payload: ExperimentObservationRequest, db: AsyncSession = Depends(get_db)):
    exp = await db.get(ContentExperiment, UUID(experiment_id))
    if not exp:
        raise HTTPException(404, "Experiment not found")
    try:
        obs = await engine.observe(db, exp, payload.model_dump(mode="json"))
        return {"id": str(obs.id), "experiment_id": str(obs.experiment_id), "variant_key": obs.variant_key, "observed_at": obs.observed_at}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{experiment_id}/evaluate")
async def evaluate_experiment(experiment_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await engine.evaluate(db, experiment_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{experiment_id}/close")
async def close_experiment(experiment_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await engine.close(db, experiment_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
