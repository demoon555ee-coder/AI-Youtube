from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import Request

from app.config import settings


def metrics_token_matches(request: Request) -> bool:
    supplied = request.headers.get("X-Metrics-Token", "").strip()
    if not supplied:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
    if not supplied:
        return False
    token_path = Path(settings.metrics_auth_token_file)
    try:
        expected = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(expected) and hmac.compare_digest(supplied, expected)
