from __future__ import annotations

from urllib.parse import urlparse


def validate_remote_url(value: str, *, allowed_hosts: set[str] | None = None) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Remote provider URL must use http/https with a hostname")
    host = parsed.hostname.lower()
    if allowed_hosts is not None and host not in {h.lower() for h in allowed_hosts if h}:
        raise ValueError(f"Provider returned a URL outside the configured allowlist: {host}")
    return value
