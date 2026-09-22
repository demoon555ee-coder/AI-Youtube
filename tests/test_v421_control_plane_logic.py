from pathlib import Path

from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]

import pytest

from app.governance.service import AgentGovernanceService, DEFAULT_ACTIONS
from app.planner.service import AgentPlannerService
from app.learning.service import FORBIDDEN_STRATEGY_KEYS


def test_governance_actions_have_explicit_safe_defaults():
    assert DEFAULT_ACTIONS["research"]["automation_mode"] == "auto"
    assert DEFAULT_ACTIONS["production"]["automation_mode"] == "approve"
    assert DEFAULT_ACTIONS["full_rebuild"]["automation_mode"] == "block"


def test_requested_mode_contract_is_closed():
    from app.governance.service import _requested_mode
    for mode in ("auto", "approve", "defer", "block"):
        assert _requested_mode(mode) == mode
    with pytest.raises(ValueError):
        _requested_mode("anything")


def test_planner_rejects_cycles():
    with pytest.raises(ValueError, match="cycle"):
        AgentPlannerService._validate_acyclic([
            {"node_key": "a", "deps": ["c"]},
            {"node_key": "b", "deps": ["a"]},
            {"node_key": "c", "deps": ["b"]},
        ])


def test_planner_accepts_dag():
    AgentPlannerService._validate_acyclic([
        {"node_key": "a", "deps": []},
        {"node_key": "b", "deps": ["a"]},
        {"node_key": "c", "deps": ["a"]},
    ])


def test_learning_can_never_introduce_governance_controls():
    for key in {"risk_tier", "automation_mode", "max_cost_usd", "governance", "permissions"}:
        assert key in FORBIDDEN_STRATEGY_KEYS


def test_runtime_rechecks_governance_and_requires_lease_for_terminal_state():
    text = (ROOT / "app/runtime/service.py").read_text()
    assert "evaluate_action" in text
    assert "policy_changed" in text
    assert 'def complete(' in text and 'lease_token: str' in text
    assert 'def fail(' in text and 'lease_token: str' in text
    assert 'await self._get_live_lease(task_id, lease_token)' in text


def test_runtime_tasks_record_channel_organization():
    text = (ROOT / "app/runtime/service.py").read_text()
    assert 'organization_id=(await self._get_channel(channel_id)).organization_id' in text


def test_runtime_api_has_no_duplicate_budget_argument_and_restricts_worker_mutation():
    text = (ROOT / "app/api/runtime.py").read_text()
    assert '**payload.model_dump(),\n            budget_usd=' not in text
    assert '"owner", "admin"' in text
    assert '"owner", "admin", "editor"' not in text


def test_execution_recheck_rejects_stale_approval():
    text = (ROOT / "app/execution/controller.py").read_text()
    assert 'approval_policy_version' in text
    assert 'approval_is_current' in text
    assert 'current_mode == "approve" and not approval_is_current' in text

def test_runtime_lease_recheck_dict_access_and_naive_datetimes():
    # Regression: acquire_lease must read governance results as a dict and must
    # compare lease timestamps against naive UTC datetimes (DB columns are naive).
    text = (ROOT / "app/runtime/service.py").read_text(encoding="utf-8")
    assert 'if not evaluation["allowed"]:' in text
    assert "evaluation.allowed" not in text
    assert "datetime.now(timezone.utc)" not in text
    assert "from datetime import datetime, timedelta" in text
