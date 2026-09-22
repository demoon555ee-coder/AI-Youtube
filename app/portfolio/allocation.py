from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class AllocationInput:
    channel_id: str
    weight: float = 1.0
    cap_usd: float | None = None
    floor_usd: float = 0.0
    current_spend_usd: float = 0.0


def allocate_weighted_budget(total_usd: float, inputs: Iterable[AllocationInput], *, reserve_ratio: float = 0.10, max_concentration_pct: float = 50.0) -> dict[str, float]:
    rows = list(inputs)
    if not rows or total_usd <= 0:
        return {r.channel_id: 0.0 for r in rows}
    reserve = min(max(reserve_ratio, 0.0), 0.95)
    distributable = total_usd * (1.0 - reserve)
    weights = {r.channel_id: max(0.0, r.weight) for r in rows}
    if sum(weights.values()) <= 0:
        weights = {r.channel_id: 1.0 for r in rows}
    max_share = min(max(max_concentration_pct, 0.0) / 100.0, 1.0)
    caps = {r.channel_id: (None if r.cap_usd is None or r.cap_usd <= 0 else r.cap_usd) for r in rows}
    alloc = {r.channel_id: 0.0 for r in rows}

    active = set(alloc)
    remaining = distributable
    while active and remaining > 1e-9:
        total_weight = sum(weights[c] for c in active) or float(len(active))
        saturated: set[str] = set()
        for channel_id in sorted(active):
            proposed = remaining * (weights[channel_id] / total_weight)
            absolute_cap = distributable * max_share
            if caps[channel_id] is not None:
                absolute_cap = min(absolute_cap, caps[channel_id] - alloc[channel_id])
            if absolute_cap < proposed:
                alloc[channel_id] += max(0.0, absolute_cap)
                remaining -= max(0.0, absolute_cap)
                saturated.add(channel_id)
        if not saturated:
            for channel_id in sorted(active):
                alloc[channel_id] += remaining * (weights[channel_id] / total_weight)
            remaining = 0.0
        active -= saturated

    # Respect explicit floors only where they fit inside the distributable budget.
    for row in rows:
        floor = max(0.0, row.floor_usd)
        if floor > alloc[row.channel_id]:
            delta = floor - alloc[row.channel_id]
            donors = sorted((cid for cid in alloc if cid != row.channel_id), key=lambda cid: alloc[cid], reverse=True)
            for donor in donors:
                take = min(delta, max(0.0, alloc[donor] - row.floor_usd))
                alloc[donor] -= take
                alloc[row.channel_id] += take
                delta -= take
                if delta <= 1e-9:
                    break
    return {k: round(max(0.0, v), 8) for k, v in alloc.items()}


def dispatch_score(*, due_at_seconds: float, spend_ratio: float, budget_weight: float, priority: float = 0.0) -> float:
    urgency = max(0.0, due_at_seconds)
    fairness = 1.0 / max(0.1, spend_ratio / max(0.1, budget_weight))
    return round((urgency * 2.0) + (fairness * 10.0) + priority, 8)
