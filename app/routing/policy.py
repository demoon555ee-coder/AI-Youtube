from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable

TIER_ORDER = {"economy": 0, "standard": 1, "premium": 2}


@dataclass(frozen=True)
class Candidate:
    provider: str
    kind: str
    tier: str
    priority: int
    unit: str
    unit_cost_usd: float
    capabilities: dict[str, Any]
    config: dict[str, Any]
    runtime_available: bool = True

    @property
    def tier_rank(self) -> int:
        return TIER_ORDER.get(self.tier, 1)

    def estimate(self, units: float) -> float:
        return round(max(0.0, units) * max(0.0, self.unit_cost_usd), 8)


def rank_candidates(
    candidates: Iterable[Candidate],
    *,
    requested_tier: str,
    units: float,
    feasible: dict[str, bool],
    allow_quality_downgrade: bool,
) -> list[Candidate]:
    requested_rank = TIER_ORDER.get(requested_tier, 1)
    rows: list[tuple[tuple, Candidate]] = []
    for candidate in candidates:
        if not candidate.runtime_available:
            continue
        tier_ok = candidate.tier_rank >= requested_rank
        if not tier_ok and not allow_quality_downgrade:
            continue
        is_feasible = bool(feasible.get(candidate.provider, False))
        quality_penalty = 0 if tier_ok else 10 + requested_rank - candidate.tier_rank
        key = (
            0 if is_feasible else 1,
            quality_penalty,
            candidate.estimate(units),
            -candidate.priority,
            candidate.provider,
        )
        rows.append((key, candidate))
    rows.sort(key=lambda row: row[0])
    return [candidate for _, candidate in rows]
