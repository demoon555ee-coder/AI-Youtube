from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Iterable


_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, math.inf)


def _label_key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, str(v)) for k, v in labels.items()))


def _escape(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


@dataclass
class _Histogram:
    buckets: dict[float, int] = field(default_factory=lambda: {b: 0 for b in _BUCKETS})
    count: int = 0
    total: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        for bucket in _BUCKETS:
            if value <= bucket:
                self.buckets[bucket] += 1


class MetricsRegistry:
    """Small dependency-free Prometheus exposition registry.

    It intentionally keeps bounded label sets (HTTP method/route/status, provider, etc.).
    For multi-instance deployments Prometheus should scrape each instance separately.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], _Histogram] = {}

    def inc(self, name: str, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = (name, _label_key(labels or {}))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + amount

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = (name, _label_key(labels or {}))
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = (name, _label_key(labels or {}))
        with self._lock:
            histogram = self._histograms.setdefault(key, _Histogram())
            histogram.observe(float(value))

    def render(self) -> str:
        with self._lock:
            counters = list(self._counters.items())
            gauges = list(self._gauges.items())
            histograms = list(self._histograms.items())

        lines: list[str] = []
        emitted_types: set[str] = set()

        def render_labels(labels: Iterable[tuple[str, str]], extra: dict[str, str] | None = None) -> str:
            data = dict(labels)
            if extra:
                data.update(extra)
            if not data:
                return ''
            body = ','.join(f'{k}="{_escape(v)}"' for k, v in sorted(data.items()))
            return '{' + body + '}'

        for (name, labels), value in counters:
            if name not in emitted_types:
                lines.append(f'# TYPE {name} counter')
                emitted_types.add(name)
            lines.append(f'{name}{render_labels(labels)} {value}')

        for (name, labels), value in gauges:
            if name not in emitted_types:
                lines.append(f'# TYPE {name} gauge')
                emitted_types.add(name)
            lines.append(f'{name}{render_labels(labels)} {value}')

        for (name, labels), histogram in histograms:
            if name not in emitted_types:
                lines.append(f'# TYPE {name} histogram')
                emitted_types.add(name)
            for bucket, count in histogram.buckets.items():
                le = '+Inf' if math.isinf(bucket) else str(bucket)
                lines.append(f'{name}_bucket{render_labels(labels, {"le": le})} {count}')
            lines.append(f'{name}_count{render_labels(labels)} {histogram.count}')
            lines.append(f'{name}_sum{render_labels(labels)} {histogram.total}')
        return '\n'.join(lines) + '\n'


metrics = MetricsRegistry()
