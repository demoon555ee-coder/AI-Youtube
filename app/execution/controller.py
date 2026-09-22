from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import AutonomousExecutionRun, AutonomousOptimizationDecision, Channel, ContentExperiment, VideoProject, VideoQualityReport, WorkflowRun, WorkflowStep, WorkflowEvent, BudgetReservation, ContentVersion
from app.auth.security import Principal
from app.portfolio.manager import PortfolioManager
from app.evolution.service import ContentEvolutionService
from app.governance.service import AgentGovernanceService
from app.models import AgentApprovalRequest

ALLOWED_MODES = {"auto", "approve", "defer", "block"}
EXECUTABLE_SCOPES = {"scene_reedit", "packaging_experiment", "blueprint_replan", "full_rebuild"}

def has_permission(principal: Principal, permission: str) -> bool:
    return principal.auth_type == "dev-fallback" or "*" in principal.scopes or permission in principal.scopes

class AutonomousExecutionController:
    """Safely converts optimization decisions into auditable actions."""
    def __init__(self, db: AsyncSession):
        self.db = db

    async def dispatch(self, *, decision, project, channel, principal, mode: str, idempotency_key: str | None = None):
        mode = mode.lower()
        if mode not in ALLOWED_MODES:
            raise ValueError("Unsupported execution mode")
        key = idempotency_key or f"decision:{decision.id}:{mode}"
        existing = await self.db.scalar(select(AutonomousExecutionRun).where(AutonomousExecutionRun.decision_id == decision.id, AutonomousExecutionRun.idempotency_key == key))
        if existing:
            return existing
        guardrails, estimate, block_reason = await self._guardrails(decision, project, channel, principal)
        governance = await AgentGovernanceService(self.db).evaluate(
            channel=channel, decision=decision, estimate=estimate, principal=principal, requested_mode=mode
        )
        effective_mode = governance["effective_mode"]
        if block_reason:
            governance["allowed"] = False
            governance["reasons"] = list(governance["reasons"]) + [block_reason]
            effective_mode = "block"
            governance["effective_mode"] = effective_mode
        if mode == "block":
            status, reason = "BLOCKED", "Blocked by operator."
        elif mode == "defer":
            status, reason = "DEFERRED", "Deferred by operator."
        elif not governance["allowed"]:
            status, reason = "BLOCKED", "; ".join(governance["reasons"])
        elif effective_mode == "approve":
            status, reason = "APPROVAL_REQUIRED", "Human approval is required by Agent Governance."
        elif effective_mode == "auto" and not settings.optimization_auto_execute:
            status, reason = "APPROVAL_REQUIRED", "Global autonomous execution is disabled; explicit approval is required."
        else:
            status, reason = "APPROVED", "Allowed by Agent Governance and execution guardrails."
        run = AutonomousExecutionRun(organization_id=channel.organization_id, channel_id=channel.id, project_id=project.id, decision_id=decision.id, mode=effective_mode, status=status, idempotency_key=key, target_scope=decision.target_scope, estimated_cost_usd=estimate, requested_by_user_id=principal.user_id, reason=reason, guardrails=guardrails + ["agent_governance", f"risk:{governance['risk_tier']}"])
        self.db.add(run); await self.db.flush()
        governance["effective_mode"] = effective_mode
        await AgentGovernanceService(self.db).journal(channel=channel, decision=decision, run=run, evaluation=governance, event_type="DISPATCH_EVALUATED", principal=principal, allowed=governance["allowed"] and status != "BLOCKED")
        if status == "APPROVAL_REQUIRED":
            await AgentGovernanceService(self.db).create_approval(channel=channel, run=run, evaluation=governance)
        elif status == "APPROVED":
            decision.status = "APPROVED"
            await self._reserve(run, channel, project, estimate)
            if effective_mode == "auto" and settings.optimization_auto_execute:
                await self._execute_locked(run, decision, project, channel)
        await self.db.flush(); return run

    async def execute(self, *, run, decision, project, channel, principal):
        if not has_permission(principal, "content:write"):
            raise PermissionError("content:write permission required")
        if run.status not in {"APPROVED", "APPROVAL_REQUIRED"}:
            return run
        guardrails, estimate, block_reason = await self._guardrails(decision, project, channel, principal)
        governance = await AgentGovernanceService(self.db).evaluate(
            channel=channel, decision=decision, estimate=estimate, principal=principal, requested_mode=run.mode
        )
        run.guardrails = guardrails + ["agent_governance", f"risk:{governance['risk_tier']}"]; run.estimated_cost_usd = estimate
        approval = await self.db.scalar(
            select(AgentApprovalRequest)
            .where(AgentApprovalRequest.execution_run_id == run.id)
            .order_by(AgentApprovalRequest.requested_at.desc())
        )
        approval_policy_version = int((approval.metadata_json or {}).get("policy_version", 0)) if approval else 0
        approval_is_current = bool(approval and approval.status == "APPROVED" and approval_policy_version == int(governance["policy_version"]))
        current_mode = governance["effective_mode"]
        if block_reason or not governance["allowed"] or current_mode in {"block", "defer"}:
            reason = block_reason or "; ".join(governance["reasons"])
            run.status = "BLOCKED"; run.reason = reason; run.error_message = reason
            await AgentGovernanceService(self.db).journal(channel=channel, decision=decision, run=run, evaluation=governance, event_type="EXECUTE_BLOCKED", principal=principal, allowed=False)
            await self.db.flush(); return run
        if current_mode == "approve" and not approval_is_current:
            run.status = "APPROVAL_REQUIRED"
            run.reason = "Current Agent Governance policy requires a fresh human approval."
            await AgentGovernanceService(self.db).create_approval(channel=channel, run=run, evaluation=governance)
            await AgentGovernanceService(self.db).journal(channel=channel, decision=decision, run=run, evaluation=governance, event_type="EXECUTE_DENIED_NO_CURRENT_APPROVAL", principal=principal, allowed=False)
            await self.db.flush()
            return run
        if run.status == "APPROVAL_REQUIRED" and not approval_is_current:
            run.reason = "Execution requires an approved human approval request matching the current governance policy."
            await AgentGovernanceService(self.db).journal(channel=channel, decision=decision, run=run, evaluation=governance, event_type="EXECUTE_DENIED_NO_APPROVAL", principal=principal, allowed=False)
            await self.db.flush()
            return run
        if current_mode == "auto" and not settings.optimization_auto_execute:
            run.status = "APPROVAL_REQUIRED"
            run.reason = "Global autonomous execution is disabled; explicit approval is required."
            await AgentGovernanceService(self.db).create_approval(channel=channel, run=run, evaluation=governance)
            await self.db.flush()
            return run
        await AgentGovernanceService(self.db).journal(channel=channel, decision=decision, run=run, evaluation=governance, event_type="EXECUTE_ALLOWED", principal=principal, allowed=True)
        if not run.reservation_id:
            await self._reserve(run, channel, project, estimate)
        return await self._execute_locked(run, decision, project, channel)

    async def defer(self, *, run):
        if run.status in {"RUNNING", "SUCCEEDED"}: raise ValueError("Execution cannot be deferred in current status")
        run.status = "DEFERRED"; run.updated_at = datetime.utcnow(); await self.db.flush(); return run

    async def _execute_locked(self, run, decision, project, channel):
        run.status = "RUNNING"; run.updated_at = datetime.utcnow()
        decision.status = "EXECUTING"
        try:
            if decision.target_scope == "packaging_experiment":
                exp = await self._create_experiment(decision, project, channel); run.experiment_id = exp.id; run.result = {"type":"packaging_experiment","experiment_id":str(exp.id)}; run.status="SUCCEEDED"
            elif decision.target_scope in EXECUTABLE_SCOPES:
                change_plan = self._change_plan(decision)
                revision, _version = await ContentEvolutionService(self.db).create_revision(source_project=project, trigger_type="autonomous_execution", reason=decision.hypothesis, change_plan=change_plan, metrics_snapshot=decision.evidence, trigger_alert_id=None)
                inherited = dict(project.data or {})
                for key in ("scene_director", "storyboard", "production", "thumbnail"):
                    if key in inherited:
                        revision.data[key] = inherited[key]
                revision.data["evolution"]["execution_mode"] = "targeted_scene_reedit" if decision.target_scope == "scene_reedit" else "standard_revision"
                workflow = await self._create_workflow(revision.id, f"execution:{run.id}")
                run.workflow_id = workflow.id; run.revision_project_id = revision.id; run.result = {"type":decision.target_scope,"revision_project_id":str(revision.id),"workflow_id":str(workflow.id)}
                run.status = "RUNNING"
            else:
                run.status = "NO_ACTION"; run.result = {"type":"no_action"}
            if run.status == "SUCCEEDED":
                run.completed_at = datetime.utcnow(); decision.status = "EXECUTED"
            await self.db.flush(); return run
        except Exception as exc:
            run.status = "FAILED"; run.error_message = str(exc); run.completed_at = datetime.utcnow()
            if run.reservation_id:
                reservation = await self.db.get(BudgetReservation, run.reservation_id, with_for_update=True)
                if reservation and reservation.status == "ACTIVE":
                    reservation.status = "RELEASED"; reservation.released_at = datetime.utcnow()
            decision.status = "EXECUTION_FAILED"
            await self.db.flush(); raise

    async def _create_workflow(self, project_id: UUID, idempotency_key: str):
        existing = await self.db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == idempotency_key))
        if existing:
            if existing.project_id != project_id:
                raise ValueError("Execution workflow idempotency key belongs to another project")
            return existing
        active = await self.db.scalar(select(WorkflowRun).where(WorkflowRun.project_id == project_id, WorkflowRun.status.in_({"QUEUED", "RUNNING"})).order_by(WorkflowRun.created_at.desc()).limit(1))
        if active:
            return active
        run = WorkflowRun(project_id=project_id, idempotency_key=idempotency_key)
        self.db.add(run)
        await self.db.flush()
        from app.workflows.engine import WORKFLOW_STEPS
        for order, (step_key, _status) in enumerate(WORKFLOW_STEPS):
            self.db.add(WorkflowStep(workflow_run_id=run.id, step_key=step_key, step_order=order))
        self.db.add(WorkflowEvent(workflow_run_id=run.id, project_id=project_id, event_type="workflow.queued", payload={"source":"autonomous_execution"}))
        return run

    async def reconcile_workflow(self, workflow_id: UUID, *, success: bool, result: dict[str, Any] | None = None) -> None:
        run = await self.db.scalar(select(AutonomousExecutionRun).where(AutonomousExecutionRun.workflow_id == workflow_id).with_for_update())
        if not run or run.status in {"SUCCEEDED","FAILED","BLOCKED","CANCELLED"}: return
        run.status = "SUCCEEDED" if success else "FAILED"; run.result = {**(run.result or {}), **(result or {})}; run.error_message = None if success else str((result or {}).get("error") or "Workflow execution failed"); run.completed_at = datetime.utcnow(); run.updated_at = datetime.utcnow()
        if success:
            decision = await self.db.get(AutonomousOptimizationDecision, run.decision_id, with_for_update=True)
            if decision:
                decision.status = "EXECUTED"
        reservation = await self.db.get(BudgetReservation, run.reservation_id) if run.reservation_id else None
        if reservation and reservation.status == "ACTIVE":
            reservation.status = "RELEASED"
            reservation.released_at = datetime.utcnow()
        await self.db.flush()

    async def _guardrails(self, decision, project, channel, principal):
        guardrails=["content:write","published_source_immutable","requires_quality_gate","budget_check","idempotent_execution","tenant_scoped"]
        if not settings.execution_controller_enabled: return guardrails,0.0,"Autonomous execution controller is disabled."
        if decision.status in {"BLOCKED","NO_ACTION"}: return guardrails,0.0,"Optimization decision is not executable."
        if not has_permission(principal,"content:write"): return guardrails,0.0,"content:write permission required."
        if decision.target_scope not in EXECUTABLE_SCOPES: return guardrails,0.0,"Decision target is not executable."
        if project.status not in {"READY_TO_PUBLISH", "PUBLISHED", "COMPLETED"}: return guardrails,0.0,"Source project is not in an executable terminal state."
        if float(decision.confidence or 0) < float(settings.optimization_min_confidence): return guardrails,0.0,"Decision confidence is below the execution threshold."
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        revisions_today = int(await self.db.scalar(select(func.count(VideoProject.id)).where(VideoProject.channel_id == channel.id, VideoProject.revision_number > 0, VideoProject.created_at >= day_start)) or 0)
        if revisions_today >= int(settings.execution_max_revisions_per_day): return guardrails,0.0,"Daily autonomous revision limit reached."
        if settings.execution_require_quality_gate:
            q=await self.db.scalar(select(VideoQualityReport).where(VideoQualityReport.project_id==project.id).order_by(VideoQualityReport.created_at.desc()))
            if not q: return guardrails,0.0,"A successful Quality Gate report is required before execution."
            if q.status=="FAIL": return guardrails,0.0,"Latest Quality Gate failed."
        return guardrails,self._estimate(project.data or {},decision.target_scope),None

    async def _reserve(self, run, channel, project, amount):
        if amount<=0:return
        reservation=await PortfolioManager(self.db).reserve(channel.owner_id,amount_usd=amount,idempotency_key=f"execution:{run.id}",channel_id=channel.id,project_id=project.id,purpose=f"autonomous:{run.target_scope}",ttl_minutes=max(1,settings.execution_default_reservation_ttl_minutes))
        run.reservation_id=reservation.id

    @staticmethod
    def _estimate(data,scope):
        plan=data.get("routing_plan") or {}
        if scope=="packaging_experiment": return 0.0
        if scope=="scene_reedit": return round(float((plan.get("production") or {}).get("estimated_cost_usd",0) or 0)+float((plan.get("editor") or {}).get("estimated_cost_usd",0) or 0),8)
        return round(sum(float((plan.get(k) or {}).get("estimated_cost_usd",0) or 0) for k in ["research","script","storyboard","scene_director","production","production_video","tts","editor","thumbnail","qa"]),8)

    async def _create_experiment(self,decision,project,channel):
        text=str((decision.action_plan or {}).get("actions") or []).lower(); dimension="thumbnail"
        if "title" in text:dimension="title"
        elif "hook" in text:dimension="hook"
        elif "pacing" in text:dimension="pacing"
        row=ContentExperiment(channel_id=channel.id,video_project_id=project.id,experiment_type="observational",dimension=dimension,hypothesis=decision.hypothesis,variants={"control":{"label":"Control","title":(project.data or {}).get("title") or project.topic},"variant_a":{"label":"AI Variant A","strategy":"apply optimization hypothesis"}},decision_rule={"primary_metric":"ctr" if dimension in {"title","thumbnail"} else "average_view_percentage","minimum_observations":2,"source_decision_id":str(decision.id)},status="DRAFT")
        self.db.add(row); await self.db.flush(); return row

    @staticmethod
    def _change_plan(decision):
        return {"mode":decision.target_scope,"objective":decision.hypothesis,"actions":(decision.action_plan or {}).get("actions") or [],"evidence":decision.evidence or {},"do_not_modify_source":True}

def serialize_execution(run):
    return {"id":str(run.id),"decision_id":str(run.decision_id),"organization_id":str(run.organization_id) if run.organization_id else None,"channel_id":str(run.channel_id),"project_id":str(run.project_id),"workflow_id":str(run.workflow_id) if run.workflow_id else None,"revision_project_id":str(run.revision_project_id) if run.revision_project_id else None,"experiment_id":str(run.experiment_id) if run.experiment_id else None,"reservation_id":str(run.reservation_id) if run.reservation_id else None,"mode":run.mode,"status":run.status,"idempotency_key":run.idempotency_key,"target_scope":run.target_scope,"estimated_cost_usd":run.estimated_cost_usd,"reason":run.reason,"guardrails":run.guardrails or [],"result":run.result or {},"error_message":run.error_message,"created_at":run.created_at,"updated_at":run.updated_at,"completed_at":run.completed_at}
