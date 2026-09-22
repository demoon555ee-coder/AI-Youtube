from __future__ import annotations

import contextvars
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass


_trace_id = contextvars.ContextVar('trace_id', default=None)
_span_id = contextvars.ContextVar('span_id', default=None)


def _new_trace_id() -> str:
    return secrets.token_hex(16)


def _new_span_id() -> str:
    return secrets.token_hex(8)


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_span_id() -> str | None:
    return _span_id.get()


def _parse_traceparent(header: str | None) -> str | None:
    if not header:
        return None
    parts = header.strip().split('-')
    if len(parts) != 4:
        return None
    trace_id, span_id, flags = parts[1], parts[2], parts[3]
    if len(trace_id) != 32 or len(span_id) != 16:
        return None
    try:
        int(trace_id, 16); int(span_id, 16); int(flags, 16)
    except ValueError:
        return None
    if trace_id == '0' * 32 or span_id == '0' * 16:
        return None
    return trace_id


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    started_at: float

    @property
    def duration_ms(self) -> float:
        return (time.perf_counter() - self.started_at) * 1000


class Tracing:
    def start_request(self, traceparent: str | None = None) -> Span:
        trace_id = _parse_traceparent(traceparent) or _new_trace_id()
        span_id = _new_span_id()
        parent = current_span_id()
        _trace_id.set(trace_id)
        _span_id.set(span_id)
        return Span('http.request', trace_id, span_id, parent, time.perf_counter())

    @contextmanager
    def span(self, name: str):
        parent = current_span_id()
        trace_id = current_trace_id() or _new_trace_id()
        span_id = _new_span_id()
        trace_token = _trace_id.set(trace_id)
        span_token = _span_id.set(span_id)
        started = time.perf_counter()
        try:
            yield Span(name, trace_id, span_id, parent, started)
        finally:
            _span_id.reset(span_token)
            _trace_id.reset(trace_token)

    def traceparent(self) -> str | None:
        trace_id = current_trace_id()
        span_id = current_span_id()
        if not trace_id or not span_id:
            return None
        return f'00-{trace_id}-{span_id}-01'


tracing = Tracing()
