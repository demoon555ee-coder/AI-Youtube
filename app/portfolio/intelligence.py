from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CostLine:
    provider: str
    service: str
    quantity: float
    unit_cost_usd: float

    @property
    def total_cost_usd(self) -> float:
        return round(max(0.0, self.quantity) * max(0.0, self.unit_cost_usd), 8)


def total_cost(lines: Iterable[CostLine]) -> float:
    return round(sum(line.total_cost_usd for line in lines), 8)


def budget_status(*, spent_usd: float, limit_usd: float, hard_limit: bool) -> dict:
    spent = max(0.0, spent_usd)
    limit = max(0.0, limit_usd)
    if limit <= 0:
        return {"state": "UNLIMITED", "spent_usd": spent, "limit_usd": 0.0, "utilization_pct": 0.0, "remaining_usd": None, "blocked": False}
    remaining = max(0.0, limit - spent)
    utilization = round((spent / limit) * 100.0, 2)
    if spent >= limit:
        state = "BLOCKED" if hard_limit else "EXCEEDED"
    elif utilization >= 80:
        state = "WARNING"
    else:
        state = "OK"
    return {
        "state": state,
        "spent_usd": round(spent, 8),
        "limit_usd": round(limit, 8),
        "utilization_pct": utilization,
        "remaining_usd": round(remaining, 8),
        "blocked": bool(hard_limit and spent >= limit),
    }
