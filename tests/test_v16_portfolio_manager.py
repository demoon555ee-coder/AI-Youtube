from app.portfolio.allocation import AllocationInput, allocate_weighted_budget, dispatch_score


def test_weighted_allocation_respects_reserve_and_concentration():
    inputs = [
        AllocationInput("a", weight=3),
        AllocationInput("b", weight=1),
        AllocationInput("c", weight=1),
    ]
    out = allocate_weighted_budget(1000, inputs, reserve_ratio=0.10, max_concentration_pct=50)
    assert round(sum(out.values()), 2) == 900.00
    assert out["a"] <= 500
    assert out["a"] > out["b"] >= 0


def test_channel_cap_limits_allocation():
    inputs = [AllocationInput("a", weight=10, cap_usd=100), AllocationInput("b", weight=1)]
    out = allocate_weighted_budget(1000, inputs, reserve_ratio=0, max_concentration_pct=100)
    assert out["a"] == 100
    assert out["b"] == 900


def test_zero_weights_become_equal():
    out = allocate_weighted_budget(900, [AllocationInput("a", 0), AllocationInput("b", 0)], reserve_ratio=0)
    assert out == {"a": 450.0, "b": 450.0}


def test_no_budget_returns_zeroes():
    assert allocate_weighted_budget(0, [AllocationInput("a"), AllocationInput("b")]) == {"a": 0.0, "b": 0.0}


def test_dispatch_score_prefers_more_urgent_item():
    urgent = dispatch_score(due_at_seconds=100, spend_ratio=1, budget_weight=1)
    future = dispatch_score(due_at_seconds=0, spend_ratio=1, budget_weight=1)
    assert urgent > future


def test_dispatch_score_rewards_lower_relative_spend():
    low_spend = dispatch_score(due_at_seconds=0, spend_ratio=0.5, budget_weight=1)
    high_spend = dispatch_score(due_at_seconds=0, spend_ratio=5, budget_weight=1)
    assert low_spend > high_spend
