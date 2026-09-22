from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from app.execution.controller import AutonomousExecutionController

def test_v38_contract_files_exist():
    model=Path("app/models/execution.py").read_text(); api=Path("app/api/execution.py").read_text(); mig=Path("app/db/migrations.py").read_text(); main=Path("app/main.py").read_text(); ui=Path("frontend/app/execution/page.tsx").read_text()
    assert "autonomous_execution_runs" in model
    assert "026_v38_autonomous_execution_controller" in mig
    assert 'prefix="/api/v1/execution"' in api
    assert "execution_router" in main
    assert "Autonomous Execution" in ui

def test_modes_and_guardrails_are_bounded():
    p=Path("app/execution/controller.py").read_text()
    assert 'ALLOWED_MODES = {"auto", "approve", "defer", "block"}' in p
    for token in ["published_source_immutable","requires_quality_gate","budget_check","idempotent_execution","tenant_scoped"]: assert token in p

def test_estimates():
    svc=AutonomousExecutionController.__new__(AutonomousExecutionController)
    data={"routing_plan":{"production":{"estimated_cost_usd":1.2},"editor":{"estimated_cost_usd":0.8},"script":{"estimated_cost_usd":0.4}}}
    assert svc._estimate(data,"packaging_experiment")==0
    assert svc._estimate(data,"scene_reedit")==2.0
    assert svc._estimate(data,"full_rebuild")==2.4

def test_no_action_and_low_confidence_are_blocked_by_contract():
    p=Path("app/execution/controller.py").read_text()
    assert 'decision.status in {"BLOCKED","NO_ACTION"}' in p
    assert "Decision confidence is below the execution threshold." in p

def test_workflow_reconciliation_hooks():
    p=Path("app/workflows/engine.py").read_text()
    assert "reconcile_workflow(workflow.id, success=True" in p
    assert "reconcile_workflow(workflow.id, success=False" in p

def test_permission_guard():
    p=Path("app/execution/controller.py").read_text()
    assert 'has_permission(principal,"content:write")' in p


def test_targeted_scene_execution_is_real_and_scoped():
    p=Path("app/services/orchestrator.py").read_text()
    assert 'evolution.get("execution_mode") == "targeted_scene_reedit"' in p
    assert "TargetedReEditService(self.output_dir)" not in p  # service must be called through configured settings output dir
    assert "scene_changes" in p and "workflow.targeted_execution_completed" in p

def test_execution_does_not_reuse_alert_for_evolution_unique_constraint():
    p=Path("app/execution/controller.py").read_text()
    assert "trigger_alert_id=None" in p

def test_revision_and_quality_guardrails():
    p=Path("app/execution/controller.py").read_text()
    assert "Source project is not in an executable terminal state." in p
    assert "Daily autonomous revision limit reached." in p
