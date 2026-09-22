from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.security import Principal, get_current_principal, permission_dependency
from app.db.session import get_db
from app.models import AutonomousExecutionRun, AutonomousOptimizationDecision, Channel, VideoProject
from app.execution.controller import AutonomousExecutionController, serialize_execution
router=APIRouter(prefix="/api/v1/execution",tags=["autonomous-execution"])
class DispatchRequest(BaseModel):
    mode:str=Field(default="auto",pattern="^(auto|approve|defer|block)$")
    idempotency_key:str|None=Field(default=None,max_length=255)
class ExecuteRequest(BaseModel):
    idempotency_key:str|None=Field(default=None,max_length=255)
def _access(channel,principal):
    if principal.is_dev_fallback:return
    if principal.organization_id is not None and channel.organization_id==principal.organization_id:return
    if channel.owner_id==principal.scope_key:return
    raise HTTPException(404,"Resource not found")
async def _load(decision_id,db,principal):
    decision=await db.get(AutonomousOptimizationDecision,decision_id)
    if not decision:raise HTTPException(404,"Optimization decision not found")
    channel=await db.get(Channel,decision.channel_id); project=await db.get(VideoProject,decision.project_id)
    if not channel or not project:raise HTTPException(404,"Resource not found")
    _access(channel,principal);return decision,project,channel
@router.post("/decisions/{decision_id}/dispatch",status_code=201)
async def dispatch(decision_id:UUID,payload:DispatchRequest,db:AsyncSession=Depends(get_db),principal:Principal=Depends(permission_dependency("content:write"))):
    decision,project,channel=await _load(decision_id,db,principal)
    try:run=await AutonomousExecutionController(db).dispatch(decision=decision,project=project,channel=channel,principal=principal,mode=payload.mode,idempotency_key=payload.idempotency_key);await db.commit();await db.refresh(run);return serialize_execution(run)
    except PermissionError as exc:raise HTTPException(403,str(exc))
    except ValueError as exc:raise HTTPException(409,str(exc))
@router.post("/runs/{run_id}/execute")
async def execute(run_id:UUID,payload:ExecuteRequest=ExecuteRequest(),db:AsyncSession=Depends(get_db),principal:Principal=Depends(permission_dependency("content:write"))):
    run=await db.get(AutonomousExecutionRun,run_id)
    if not run:raise HTTPException(404,"Execution run not found")
    decision,project,channel=await _load(run.decision_id,db,principal)
    try:result=await AutonomousExecutionController(db).execute(run=run,decision=decision,project=project,channel=channel,principal=principal);await db.commit();await db.refresh(result);return serialize_execution(result)
    except PermissionError as exc:raise HTTPException(403,str(exc))
    except ValueError as exc:raise HTTPException(409,str(exc))
@router.post("/runs/{run_id}/defer")
async def defer(run_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(permission_dependency("content:write"))):
    run=await db.get(AutonomousExecutionRun,run_id)
    if not run:raise HTTPException(404,"Execution run not found")
    _decision,_project,channel=await _load(run.decision_id,db,principal)
    result=await AutonomousExecutionController(db).defer(run=run);await db.commit();await db.refresh(result);return serialize_execution(result)
@router.get("/projects/{project_id}/runs")
async def project_runs(project_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_current_principal)):
    project=await db.get(VideoProject,project_id)
    if not project:raise HTTPException(404,"Project not found")
    channel=await db.get(Channel,project.channel_id)
    if not channel:raise HTTPException(404,"Channel not found")
    _access(channel,principal)
    rows=await db.execute(select(AutonomousExecutionRun).where(AutonomousExecutionRun.project_id==project.id).order_by(AutonomousExecutionRun.created_at.desc()).limit(100))
    return {"project_id":str(project_id),"runs":[serialize_execution(r) for r in rows.scalars().all()]}
@router.get("/channels/{channel_id}/runs")
async def channel_runs(channel_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_current_principal)):
    channel=await db.get(Channel,channel_id)
    if not channel:raise HTTPException(404,"Channel not found")
    _access(channel,principal)
    rows=await db.execute(select(AutonomousExecutionRun).where(AutonomousExecutionRun.channel_id==channel.id).order_by(AutonomousExecutionRun.created_at.desc()).limit(100))
    return {"channel_id":str(channel_id),"runs":[serialize_execution(r) for r in rows.scalars().all()]}
