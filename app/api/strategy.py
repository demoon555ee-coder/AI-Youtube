from fastapi import APIRouter, Depends, Query

from app.auth.security import Principal, get_current_principal
from app.db.session import get_db
from app.strategy.service import PortfolioStrategyBrain

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


@router.get("/portfolio-brain")
async def portfolio_brain(
    horizon_videos: int = Query(default=20, ge=10, le=30),
    db=Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return await PortfolioStrategyBrain(db).build(
        owner_key=principal.scope_key,
        organization_id=principal.organization_id,
        horizon_videos=horizon_videos,
    )
