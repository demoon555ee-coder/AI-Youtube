from pathlib import Path

def test_v41_planner_contract_files_exist():
    assert Path("app/models/planner.py").exists()
    assert Path("app/planner/service.py").exists()
    assert Path("app/api/planner.py").exists()
    assert Path("frontend/app/planner/page.tsx").exists()
    migration = Path("app/db/migrations.py").read_text()
    for token in ["029_v41_agent_planner_dynamic_workflow_graph", "agent_plans", "agent_plan_nodes", "agent_plan_edges"]:
        assert token in migration

def test_v41_planner_has_core_controls():
    p = Path("app/planner/service.py").read_text()
    for token in ["create_plan", "_validate_acyclic", "readiness", "materialize_ready", "replan", "capability", "budget", "evaluate_action", "AgentPlanEvent"]:
        assert token in p
    assert "governance_snapshot" in p
    assert "plan_version" in p

def test_v41_api_contracts():
    p = Path("app/api/planner.py").read_text()
    for token in ["/channels/{channel_id}/plans", "/plans/{plan_id}", "/plans/{plan_id}/ready", "/plans/{plan_id}/materialize", "/plans/{plan_id}/replan"]:
        assert token in p
