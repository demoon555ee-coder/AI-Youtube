from app.portfolio.intelligence import CostLine, budget_status, total_cost


def test_cost_line_and_total_cost():
    lines = [
        CostLine("llm", "generation", 1000, 0.002),
        CostLine("tts", "voice", 2.5, 0.01),
    ]
    assert lines[0].total_cost_usd == 2.0
    assert total_cost(lines) == 2.025


def test_budget_status_warning_and_blocked():
    warn = budget_status(spent_usd=82, limit_usd=100, hard_limit=False)
    assert warn["state"] == "WARNING"
    assert warn["utilization_pct"] == 82

    blocked = budget_status(spent_usd=105, limit_usd=100, hard_limit=True)
    assert blocked["state"] == "BLOCKED"
    assert blocked["blocked"] is True
    assert blocked["remaining_usd"] == 0


def test_zero_limit_is_unlimited():
    result = budget_status(spent_usd=25, limit_usd=0, hard_limit=True)
    assert result["state"] == "UNLIMITED"
    assert result["blocked"] is False


def test_cost_math_never_goes_negative():
    assert CostLine("x", "y", -10, 5).total_cost_usd == 0
    assert CostLine("x", "y", 10, -5).total_cost_usd == 0
