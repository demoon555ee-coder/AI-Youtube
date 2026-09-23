from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.db.session import SessionLocal
from app.auth.security import Principal, get_current_principal
from app.models import Channel, WorkflowEvent, WorkflowRun, WorkflowStep, VideoProject

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


async def _get_owned_workflow(workflow_id: UUID, principal: Principal) -> WorkflowRun:
    async with SessionLocal() as db:
        run = await db.get(WorkflowRun, workflow_id)
        if not run:
            raise HTTPException(404, "Workflow not found")
        project = await db.get(VideoProject, run.project_id)
        if not project:
            raise HTTPException(404, "Workflow not found")
        channel = await db.get(Channel, project.channel_id)
        if not channel or channel.owner_id != principal.scope_key:
            raise HTTPException(404, "Workflow not found")
        return run


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: UUID, principal: Principal = Depends(get_current_principal)):
    async with SessionLocal() as db:
        run = await db.get(WorkflowRun, workflow_id)
        if not run:
            raise HTTPException(404, "Workflow not found")
        project = await db.get(VideoProject, run.project_id)
        if not project:
            raise HTTPException(404, "Workflow not found")
        channel = await db.get(Channel, project.channel_id)
        if not channel or channel.owner_id != principal.scope_key:
            raise HTTPException(404, "Workflow not found")
        q = await db.execute(
            select(WorkflowStep).where(WorkflowStep.workflow_run_id == workflow_id).order_by(WorkflowStep.step_order)
        )
        steps = list(q.scalars().all())
        return {
            "id": str(run.id),
            "project_id": str(run.project_id),
            "status": run.status,
            "attempt": run.attempt,
            "current_step": run.current_step,
            "last_error": run.last_error,
            "created_at": run.created_at,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "steps": [
                {
                    "id": str(step.id),
                    "step_key": step.step_key,
                    "step_order": step.step_order,
                    "status": step.status,
                    "attempts": step.attempts,
                    "max_attempts": step.max_attempts,
                    "error_message": step.error_message,
                    "started_at": step.started_at,
                    "finished_at": step.finished_at,
                }
                for step in steps
            ],
        }


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: UUID, principal: Principal = Depends(get_current_principal)):
    async with SessionLocal() as db:
        run = await db.get(WorkflowRun, workflow_id, with_for_update=True)
        if not run:
            raise HTTPException(404, "Workflow not found")
        project = await db.get(VideoProject, run.project_id)
        if not project:
            raise HTTPException(404, "Workflow not found")
        channel = await db.get(Channel, project.channel_id)
        if not channel or channel.owner_id != principal.scope_key:
            raise HTTPException(404, "Workflow not found")
        if run.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return {"id": str(run.id), "status": run.status, "cancelled": False}
        run.status = "CANCELLED"
        run.lease_until = None
        if project:
            project.status = "CANCELLED"
            db.add(WorkflowEvent(workflow_run_id=run.id, project_id=project.id, event_type="workflow.cancelled", payload={}))
        await db.commit()
        return {"id": str(run.id), "status": run.status, "cancelled": True}


@router.get("/{workflow_id}/events")
async def workflow_events(
    workflow_id: UUID,
    after: int = Query(default=0, ge=0),
    principal: Principal = Depends(get_current_principal),
):
    """Server-Sent Events stream. It polls PostgreSQL so it also works without Redis/WebSockets."""

    async def stream() -> AsyncIterator[str]:
        cursor = after
        idle_polls = 0
        while idle_polls < 90:
            async with SessionLocal() as db:
                run = await db.get(WorkflowRun, workflow_id)
                if not run:
                    yield "event: error\ndata: {\"detail\":\"Workflow not found\"}\n\n"
                    return
                q = await db.execute(
                    select(WorkflowEvent)
                    .where(WorkflowEvent.workflow_run_id == workflow_id, WorkflowEvent.id > cursor)
                    .order_by(WorkflowEvent.id.asc())
                    .limit(100)
                )
                events = list(q.scalars().all())
                for event in events:
                    cursor = event.id
                    payload = {"id": event.id, "type": event.event_type, "payload": event.payload, "created_at": event.created_at.isoformat()}
                    yield f"id: {event.id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if run.status in {"COMPLETED", "FAILED", "CANCELLED"} and not events:
                    yield f"event: workflow.closed\ndata: {json.dumps({'status': run.status})}\n\n"
                    return
            if events:
                idle_polls = 0
            else:
                idle_polls += 1
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    # Validate access before starting the long-lived response stream.
    await _get_owned_workflow(workflow_id, principal)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
