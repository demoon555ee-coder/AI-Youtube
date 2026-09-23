from app.routing.policy import Candidate, rank_candidates


def candidate(provider, tier, cost, priority=100, available=True):
    return Candidate(provider, "mock", tier, priority, "request", cost, {"json": True}, {}, available)


def test_same_tier_prefers_lower_cost_when_both_feasible():
    items = [candidate("premium_a", "standard", 0.02, 100), candidate("standard_b", "standard", 0.005, 50)]
    ordered = rank_candidates(items, requested_tier="standard", units=1, feasible={"premium_a": True, "standard_b": True}, allow_quality_downgrade=True)
    assert [x.provider for x in ordered[:2]] == ["standard_b", "premium_a"]


def test_budget_blocked_primary_uses_fallback():
    items = [candidate("expensive", "premium", 0.50, 200), candidate("local", "economy", 0.0, 10)]
    ordered = rank_candidates(items, requested_tier="premium", units=1, feasible={"expensive": False, "local": True}, allow_quality_downgrade=True)
    assert ordered[0].provider == "local"
    assert ordered[0].tier == "economy"


def test_quality_downgrade_disabled_removes_lower_tiers():
    items = [candidate("local", "economy", 0.0), candidate("standard", "standard", 0.01)]
    ordered = rank_candidates(items, requested_tier="premium", units=1, feasible={"local": True, "standard": True}, allow_quality_downgrade=False)
    assert ordered == []


def test_unavailable_provider_is_ignored():
    items = [candidate("dead", "premium", 0.0, available=False), candidate("live", "standard", 0.01)]
    ordered = rank_candidates(items, requested_tier="standard", units=1, feasible={"dead": True, "live": True}, allow_quality_downgrade=True)
    assert ordered[0].provider == "live"


def test_runway_key_format_requires_provider_shape():
    from app.routing.service import _is_valid_runway_api_key

    assert _is_valid_runway_api_key("key_" + "a" * 128)
    assert _is_valid_runway_api_key("KEY_" + "A" * 128)
    assert not _is_valid_runway_api_key("key_short")
    assert not _is_valid_runway_api_key("key_" + "a" * 127)


def test_runway_runtime_availability_rejects_invalid_config_key(monkeypatch):
    from app.routing.service import ProviderRouter

    monkeypatch.setattr("app.routing.service.settings.runway_api_key", "key_short", raising=False)
    candidate_obj = candidate("runway", "premium", 0.01)
    candidate_obj.kind = "runway"
    candidate_obj.capabilities = {"video": True, "generative": True}
    router = ProviderRouter.__new__(ProviderRouter)
    assert router._runtime_available(candidate_obj) is False
