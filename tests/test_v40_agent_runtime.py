from pathlib import Path

def test_v40_runtime_contract_files_exist():
    assert Path("app/models/agent_runtime.py").exists()
    assert Path("app/runtime/service.py").exists()
    assert Path("app/api/runtime.py").exists()
    assert Path("frontend/app/agents/page.tsx").exists()
    migration = Path("app/db/migrations.py").read_text()
    for token in ["028_v40_multi_agent_runtime", "agent_definitions", "agent_tasks", "agent_task_dependencies", "agent_leases", "agent_handoffs", "agent_budget_ledger"]:
        assert token in migration

def test_v40_runtime_has_core_controls():
    p = Path("app/runtime/service.py").read_text()
    for token in ["create_task", "readiness", "acquire_lease", "heartbeat", "delegate", "handoff", "reserve_budget", "ensure_agents"]:
        assert f"def {token}" in p or f"async def {token}" in p
    api = Path("app/api/runtime.py").read_text()
    assert "lease_token" in api
    assert "governance_approved" in api
    assert "action_type" in api
    assert "governance_blocked" in Path("app/runtime/service.py").read_text()

def test_v40_api_contracts():
    p=Path("app/api/runtime.py").read_text()
    for token in ["/channels/{channel_id}/agents", "/channels/{channel_id}/tasks", "/tasks/{task_id}/lease", "/tasks/{task_id}/heartbeat", "/tasks/{task_id}/delegate", "/tasks/{task_id}/handoff"]:
        assert token in p
