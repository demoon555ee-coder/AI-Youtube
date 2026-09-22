from pathlib import Path

def test_v42_learning_contract_files_exist():
    assert Path("app/models/learning.py").exists()
    assert Path("app/learning/service.py").exists()
    assert Path("app/api/learning.py").exists()
    assert Path("frontend/app/learning/page.tsx").exists()
    migration = Path("app/db/migrations.py").read_text()
    for token in ["030_v42_agent_learning_self_improvement", "agent_learning_observations", "agent_learning_evaluations", "agent_strategy_proposals", "agent_strategy_versions"]:
        assert token in migration

def test_v42_learning_has_closed_loop_and_governance_boundary():
    p = Path("app/learning/service.py").read_text()
    for token in ["record_task_outcome", "evaluate", "propose", "propose_recent", "approve_proposal", "reject_proposal", "activate", "active_strategy"]:
        assert token in p
    for token in ["risk_tier", "automation_mode", "require_human_approval", "max_cost_usd", "min_confidence", "kill_switch", "governance", "permissions"]:
        assert token in p
    assert "PENDING_APPROVAL" in p
    assert "Only approved strategy proposals can be activated" in p

def test_v42_api_contracts():
    p = Path("app/api/learning.py").read_text()
    for token in ["/channels/{channel_id}/observations", "/channels/{channel_id}/proposals", "/proposals/{proposal_id}/approve", "/proposals/{proposal_id}/reject", "/proposals/{proposal_id}/activate"]:
        assert token in p
