from pathlib import Path

def test_v39_governance_contract_files_exist():
    model = Path("app/models/governance.py").read_text()
    service = Path("app/governance/service.py").read_text()
    api = Path("app/api/governance.py").read_text()
    mig = Path("app/db/migrations.py").read_text()
    main = Path("app/main.py").read_text()
    ui = Path("frontend/app/governance/page.tsx").read_text()
    assert "agent_governance_policies" in model
    assert "agent_action_policies" in model
    assert "agent_approval_requests" in model
    assert "agent_governance_events" in model
    assert "027_v39_agent_governance_human_oversight" in mig
    assert 'prefix="/api/v1/governance"' in api
    assert "governance_router" in main
    assert "Agent Governance & Human Oversight" in ui

def test_v39_risk_tiers_and_defaults():
    p=Path("app/governance/service.py").read_text()
    for token in ['"LOW"', '"MEDIUM"', '"HIGH"', '"CRITICAL"', '"packaging_experiment"', '"scene_reedit"', '"blueprint_replan"', '"full_rebuild"']:
        assert token in p
    assert '"full_rebuild": {"risk_tier": "CRITICAL"' in p
    assert '"automation_mode": "block"' in p

def test_v39_kill_switch_and_reason_journal():
    p=Path("app/governance/service.py").read_text()
    assert "emergency_kill_switch" in p
    assert "Global Agent Governance kill switch is active." in p
    assert "evaluate_action" in p
    assert "Action passed governance for autonomous execution." in p
    assert "effective_mode" in p
    assert "journal" in p
    assert "policy_version" in p

def test_v39_approval_is_required_before_execution():
    p=Path("app/execution/controller.py").read_text()
    assert "Agent Governance" in p
    assert 'approval_is_current' in p
    assert 'policy_version' in p
    assert "EXECUTE_DENIED_NO_APPROVAL" in p

def test_v39_per_channel_policy_and_queue_endpoints():
    p=Path("app/api/governance.py").read_text()
    for token in ["/channels/{channel_id}/policy", "/channels/{channel_id}/actions/{action_type}", "/channels/{channel_id}/approvals", "/approvals/{approval_id}/approve", "/approvals/{approval_id}/reject", "/channels/{channel_id}/kill-switch", "/channels/{channel_id}/journal"]:
        assert token in p
